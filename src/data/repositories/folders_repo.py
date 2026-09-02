"""Repository managing system and user-defined custom folders."""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from src.data.database.db_manager import db_manager
from src.data.api.models import VKDialogItem
from src.core.logger import logger


@dataclass
class FolderItem:
    """Represents a conversation folder tab."""
    id: str
    title: str
    is_system: bool = False
    system_key: str = ""  # 'all', 'chats', 'pm', 'channels', 'archive', 'business', 'groups', 'custom'
    peer_ids: List[int] = field(default_factory=list)


SYSTEM_FOLDERS: List[FolderItem] = [
    FolderItem(id="system_all", title="Все", is_system=True, system_key="all"),
    FolderItem(id="system_chats", title="Чаты", is_system=True, system_key="chats"),
    FolderItem(id="system_pm", title="ЛС", is_system=True, system_key="pm"),
    FolderItem(id="system_channels", title="Каналы", is_system=True, system_key="channels"),
    FolderItem(id="system_archive", title="Архив", is_system=True, system_key="archive"),
    FolderItem(id="system_business", title="Бизнес", is_system=True, system_key="business"),
    FolderItem(id="system_groups", title="Группы", is_system=True, system_key="groups"),
]


class FoldersRepository:
    """Coordinates system and local custom dialog folders."""

    def __init__(self):
        self._custom_folders: List[FolderItem] = []

    async def load_folders(self) -> List[FolderItem]:
        """Loads all available folders (system defaults + user SQLite custom folders)."""
        db_folders = await db_manager.get_custom_folders()
        self._custom_folders = [
            FolderItem(
                id=f"custom_{f['id']}",
                title=f["title"],
                is_system=False,
                system_key="custom",
                peer_ids=f.get("peer_ids", [])
            )
            for f in db_folders
        ]
        return list(SYSTEM_FOLDERS) + self._custom_folders

    async def create_custom_folder(self, title: str, peer_ids: List[int]) -> FolderItem:
        """Saves a new user custom folder locally."""
        db_id = await db_manager.save_custom_folder(title.strip(), peer_ids)
        folder = FolderItem(
            id=f"custom_{db_id}",
            title=title.strip(),
            is_system=False,
            system_key="custom",
            peer_ids=peer_ids
        )
        self._custom_folders.append(folder)
        logger.info("Custom folder created: %s (id=%s)", title, folder.id)
        return folder

    async def delete_custom_folder(self, folder_id: str) -> None:
        """Deletes a custom folder by its id (e.g. 'custom_1')."""
        if not folder_id.startswith("custom_"):
            return
        db_id = int(folder_id.replace("custom_", ""))
        await db_manager.delete_custom_folder(db_id)
        self._custom_folders = [f for f in self._custom_folders if f.id != folder_id]
        logger.info("Custom folder deleted: %s", folder_id)

    def filter_dialogs(self, dialogs: List[VKDialogItem], folder_id: Optional[str]) -> List[VKDialogItem]:
        """
        Applies filtering rules:
        - 'system_archive': returns only archived dialogs (d.is_archived == True)
        - all other folders: exclude archived dialogs (d.is_archived == False)
        - if folder_id is None or 'system_all': return all non-archived dialogs
        - if 'system_chats': peer_id > 2000000000 (group chats/conversations)
        - if 'system_pm': 0 < peer_id < 2000000000 (direct private messages)
        - if 'system_groups': peer_id < 0 (communities)
        - if 'system_channels': channels (communities marked or named channel)
        - if 'system_business': empty
        - if custom folder: peer_id in folder.peer_ids
        """
        if folder_id == "system_archive":
            return [d for d in dialogs if d.is_archived]

        # For all other folders, exclude archived dialogs
        active_dialogs = [d for d in dialogs if not d.is_archived]

        if not folder_id or folder_id == "system_all":
            return active_dialogs

        if folder_id == "system_chats":
            return [d for d in active_dialogs if d.peer_id > 2000000000]

        if folder_id == "system_pm":
            return [d for d in active_dialogs if 0 < d.peer_id < 2000000000]

        if folder_id == "system_groups":
            return [d for d in active_dialogs if d.peer_id < 0]

        if folder_id == "system_channels":
            return [d for d in active_dialogs if d.peer_id < 0 and ("канал" in d.title.lower() or "channel" in d.title.lower())]

        if folder_id == "system_business":
            return []

        # Find in custom folders
        for cf in self._custom_folders:
            if cf.id == folder_id:
                return [d for d in active_dialogs if d.peer_id in cf.peer_ids]

        return active_dialogs


folders_repo = FoldersRepository()
