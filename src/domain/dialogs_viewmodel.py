"""Dialogs list ViewModel managing conversation list, archive rules, users cache, pinned chats, and local caching."""
import time
from typing import List, Dict, Any, Optional
from kivy.properties import ListProperty, StringProperty, BooleanProperty
from src.domain.base_viewmodel import BaseViewModel
from src.data.repositories.dialogs_repo import dialogs_repo
from src.data.repositories.folders_repo import folders_repo, FolderItem, SYSTEM_FOLDERS
from src.data.repositories.users_repo import users_repo
from src.data.api.models import VKDialogItem
from src.core.events import event_bus
from src.core.constants import EventType
from src.utils.formatters import format_timestamp, truncate_text, get_user_initials, format_unread_count
from src.utils.async_tools import run_async


class DialogsViewModel(BaseViewModel):
    """Manages conversations list, local-first updates, archive filtering, pinned chats, and 12h user caching."""

    dialogs = ListProperty([])
    folders = ListProperty([])
    active_folder_id = StringProperty("system_all")
    is_refreshing = BooleanProperty(False)
    is_loading_more = BooleanProperty(False)
    has_more = BooleanProperty(True)

    TARGET_FOLDER_COUNT = 20

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all_dialogs: List[VKDialogItem] = []
        self._peer_archive_status: Dict[int, bool] = {}
        self._peer_last_archive_check: Dict[int, float] = {}

        # Pre-populate system folders on main thread immediately
        self._update_folders_data(SYSTEM_FOLDERS)

        # Local events
        event_bus.subscribe(EventType.NEW_MESSAGE, self._on_new_message)
        event_bus.subscribe(EventType.MESSAGE_READ, self._on_message_read)

    def load_dialogs(self):
        """Loads folders and cached dialogs first, then triggers initial network fetch."""
        async def _load_flow():
            f_list = await folders_repo.load_folders()
            cached = await dialogs_repo.get_cached_dialogs()
            fresh = await dialogs_repo.fetch_dialogs(offset=0, count=40)
            return f_list, cached, fresh

        def _on_success(result):
            f_list, cached, fresh = result
            self._update_folders_data(f_list)
            items = fresh if fresh else cached
            if self._all_dialogs:
                self._merge_and_set_dialogs(items)
            else:
                for d in items:
                    self._peer_archive_status[d.peer_id] = d.is_archived
                self._sort_and_set_all_dialogs(items)

            self._apply_folder_filter()

            # Auto-fill folder if needed
            if self.active_folder_id not in ("system_all", "system_business", "system_channels") and len(self.dialogs) < self.TARGET_FOLDER_COUNT and self.has_more:
                self.load_more_dialogs(target_folder_count=self.TARGET_FOLDER_COUNT)

        self.run_task(_load_flow(), on_success=_on_success, show_loader=not bool(self._all_dialogs))

    def _merge_and_set_dialogs(self, new_items: List[VKDialogItem]):
        """Merges incoming dialogs with existing in-memory dialogs to preserve all folders (including archive)."""
        existing_dict = {d.peer_id: d for d in self._all_dialogs}
        for item in new_items:
            self._peer_archive_status[item.peer_id] = item.is_archived
            existing_dict[item.peer_id] = item
        self._sort_and_set_all_dialogs(list(existing_dict.values()))

    def refresh_dialogs(self):
        """Pulls latest dialogs on user explicit refresh button."""
        self.is_refreshing = True
        self.has_more = True

        async def _fetch():
            f_list = await folders_repo.load_folders()
            filter_param = "archive" if self.active_folder_id == "system_archive" else None
            fresh = await dialogs_repo.fetch_dialogs(offset=0, count=40, filter=filter_param)
            return f_list, fresh

        def _on_success(result):
            self.is_refreshing = False
            f_list, items = result
            self._update_folders_data(f_list)
            self._merge_and_set_dialogs(items)
            self._apply_folder_filter()

        def _on_error(exc: Exception):
            self.is_refreshing = False

        self.run_task(_fetch(), on_success=_on_success, on_error=_on_error, show_loader=False)

    def load_more_dialogs(self, target_folder_count: Optional[int] = None):
        """Loads next batch of dialogs. For folders, continues fetching until target count is reached."""
        if self.is_loading_more or not self.has_more or self.active_folder_id in ("system_business", "system_channels"):
            return

        self.is_loading_more = True
        filter_param = "archive" if self.active_folder_id == "system_archive" else None

        async def _fetch_loop():
            while self.has_more:
                if filter_param == "archive":
                    offset = len([d for d in self._all_dialogs if d.is_archived])
                else:
                    offset = len([d for d in self._all_dialogs if not d.is_archived])

                batch = await dialogs_repo.fetch_dialogs(offset=offset, count=40, filter=filter_param)
                if not batch or len(batch) < 40:
                    self.has_more = False

                existing_peers = {d.peer_id for d in self._all_dialogs}
                for item in batch:
                    self._peer_archive_status[item.peer_id] = item.is_archived
                    if item.peer_id not in existing_peers:
                        self._all_dialogs.append(item)
                        existing_peers.add(item.peer_id)

                if target_folder_count:
                    filtered = folders_repo.filter_dialogs(self._all_dialogs, self.active_folder_id)
                    if len(filtered) >= target_folder_count:
                        break
                else:
                    break

            return True

        def _on_done(res):
            self.is_loading_more = False
            self._apply_folder_filter()

        def _on_err(exc):
            self.is_loading_more = False

        self.run_task(_fetch_loop(), on_success=_on_done, on_error=_on_err, show_loader=False)

    def select_folder(self, folder_id: str):
        """Switches active folder and handles archive loading or auto-fetching."""
        if self.active_folder_id == folder_id and folder_id != "system_all":
            self.active_folder_id = "system_all"
        else:
            self.active_folder_id = folder_id

        # Apply local filter immediately for instant UI response
        self._apply_folder_filter()

        # Business and Channels are unsupported placeholders: do not run background queries
        if self.active_folder_id in ("system_business", "system_channels"):
            return

        if self.active_folder_id == "system_archive":
            self._load_archive_dialogs()
        else:
            if len(self.dialogs) < self.TARGET_FOLDER_COUNT and self.has_more:
                self.load_more_dialogs(target_folder_count=self.TARGET_FOLDER_COUNT)

    def _load_archive_dialogs(self):
        """Fetches archive conversations from VK API using filter=archive."""
        async def _fetch():
            return await dialogs_repo.fetch_dialogs(offset=0, count=40, filter="archive")

        def _on_success(archived_items: List[VKDialogItem]):
            existing_peers = {d.peer_id for d in self._all_dialogs}
            for item in archived_items:
                self._peer_archive_status[item.peer_id] = True
                if item.peer_id in existing_peers:
                    for d in self._all_dialogs:
                        if d.peer_id == item.peer_id:
                            d.is_archived = True
                            d.last_message_text = item.last_message_text
                            d.last_message_time = item.last_message_time
                            break
                else:
                    self._all_dialogs.append(item)
                    existing_peers.add(item.peer_id)
            self._apply_folder_filter()

        self.run_task(_fetch(), on_success=_on_success, show_loader=False)

    def add_custom_folder(self, title: str, peer_ids: List[int]):
        """Creates a new user custom folder and selects it."""
        if not title.strip():
            return

        async def _create():
            new_f = await folders_repo.create_custom_folder(title, peer_ids)
            all_f = await folders_repo.load_folders()
            return new_f, all_f

        def _on_created(res):
            new_f, all_f = res
            self._update_folders_data(all_f)
            self.select_folder(new_f.id)

        self.run_task(_create(), on_success=_on_created, show_loader=False)

    def remove_custom_folder(self, folder_id: str):
        """Deletes a custom folder."""
        async def _delete():
            await folders_repo.delete_custom_folder(folder_id)
            return await folders_repo.load_folders()

        def _on_deleted(all_f):
            self._update_folders_data(all_f)
            self.select_folder("system_all")

        self.run_task(_delete(), on_success=_on_deleted, show_loader=False)

    def _sort_and_set_all_dialogs(self, items: List[VKDialogItem]):
        """Sorts dialogs so pinned items are always at the top."""
        self._all_dialogs = sorted(
            items,
            key=lambda d: (1 if d.is_pinned else 0, d.last_message_time),
            reverse=True
        )

    def _update_folders_data(self, f_list: List[FolderItem]):
        """Formats folder items for UI presentation."""
        data = []
        for f in f_list:
            data.append({
                "id": f.id,
                "title": f.title,
                "is_system": f.is_system,
                "system_key": f.system_key,
                "peer_ids": f.peer_ids
            })
        self.folders = data

    def _apply_folder_filter(self):
        """Filters cached dialogs based on active_folder_id, respecting archive rules."""
        filtered = folders_repo.filter_dialogs(self._all_dialogs, self.active_folder_id)
        
        rv_data = []
        for d in filtered:
            rv_data.append({
                "peer_id": d.peer_id,
                "title": d.title,
                "initials": get_user_initials(d.title),
                "avatar_url": d.avatar_url,
                "last_message": truncate_text(d.last_message_text, max_length=60),
                "time_text": format_timestamp(d.last_message_time),
                "unread_count": d.unread_count,
                "unread_text": format_unread_count(d.unread_count),
                "is_online": d.is_online,
                "is_read": d.is_read,
                "is_outgoing": d.is_outgoing,
                "is_pinned": d.is_pinned,
                "is_archived": d.is_archived,
                "is_muted": d.is_muted
            })
        self.dialogs = rv_data

    def _on_new_message(self, peer_id: int, text: str, timestamp: int, is_out: bool, from_id: int = 0, **kwargs):
        """
        Handles incoming/outgoing new message:
        1. Checks archive status (with 5-minute cache via messages.getConversationsById).
        2. If archived, avoids raising into the general dialogs list.
        3. For chats, formats author prefix using 12h-cached users_repo.
        4. Saves message and dialog to SQLite.
        """
        from kivy.clock import Clock
        now = time.time()
        msg_id = kwargs.get("message_id", 0)
        attachments = kwargs.get("attachments", None)

        # 1. 5-minute archive check via messages.getConversationsById
        last_check = self._peer_last_archive_check.get(peer_id, 0)
        if peer_id not in self._peer_last_archive_check or (now - last_check) > 300:
            self._peer_last_archive_check[peer_id] = now
            async def _check_arch():
                is_arch = await dialogs_repo.check_conversation_archive(peer_id)
                def _apply_arch(dt):
                    self._peer_archive_status[peer_id] = is_arch
                    for d in self._all_dialogs:
                        if d.peer_id == peer_id:
                            d.is_archived = is_arch
                            break
                    self._apply_folder_filter()
                Clock.schedule_once(_apply_arch, 0)
            run_async(_check_arch())

        is_archived = self._peer_archive_status.get(peer_id, False)

        # 2. Find or create item
        target_item: Optional[VKDialogItem] = None
        for item in self._all_dialogs:
            if item.peer_id == peer_id:
                target_item = item
                is_archived = item.is_archived or is_archived
                self._all_dialogs.remove(item)
                break

        if not target_item:
            target_item = VKDialogItem(
                peer_id=peer_id,
                title=f"Диалог {peer_id}",
                last_message_text=text,
                last_message_time=timestamp,
                is_outgoing=is_out,
                is_archived=is_archived,
                unread_count=0 if is_out else 1
            )

        # 3. Format message text
        formatted_text = text or ("[Вложение]" if attachments else "")
        if is_out:
            target_item.last_message_text = f"Вы: {formatted_text}"
        else:
            if peer_id > 2000000000 and from_id > 0:
                # Group chat incoming message: get user name prefix using 12h users cache
                async def _enrich_prefix(item_ref, orig_text):
                    prefix = await users_repo.get_user_name_prefix(from_id)
                    if prefix:
                        def _apply_prefix(dt):
                            item_ref.last_message_text = f"{prefix}{orig_text}"
                            self._apply_folder_filter()
                        Clock.schedule_once(_apply_prefix, 0)

                target_item.last_message_text = formatted_text
                run_async(_enrich_prefix(target_item, formatted_text))
            else:
                target_item.last_message_text = formatted_text
            target_item.unread_count += 1

        target_item.last_message_time = timestamp
        target_item.is_outgoing = is_out
        target_item.is_read = False
        target_item.is_archived = is_archived

        # 4. Save to local SQLite
        run_async(dialogs_repo.save_dialog_new_message(
            peer_id=peer_id,
            text=target_item.last_message_text,
            timestamp=timestamp,
            is_out=is_out,
            message_id=msg_id,
            attachments=attachments,
            is_archived=is_archived
        ))

        # 5. Position dialog:
        if is_archived:
            # Archived: keep in memory list but do NOT raise above active unarchived chats
            self._all_dialogs.append(target_item)
        else:
            # Non-archived: raise to top under pinned chats
            if target_item.is_pinned:
                self._all_dialogs.insert(0, target_item)
            else:
                first_unpinned_idx = 0
                while first_unpinned_idx < len(self._all_dialogs) and self._all_dialogs[first_unpinned_idx].is_pinned:
                    first_unpinned_idx += 1
                self._all_dialogs.insert(first_unpinned_idx, target_item)

        # 6. Refresh UI locally
        self._apply_folder_filter()

    def _on_message_read(self, peer_id: int, **kwargs):
        """Updates read status locally when read event occurs."""
        for item in self._all_dialogs:
            if item.peer_id == peer_id:
                item.unread_count = 0
                item.is_read = True
                break
        self._apply_folder_filter()
