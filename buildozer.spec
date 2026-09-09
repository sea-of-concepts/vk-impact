[app]

# (str) Title of your application
title = VK IMPACT

# (str) Package name (only alphanumeric and underscores, no dashes)
package.name = vkimpact

# (str) Package domain (needed for android/ios packaging)
package.domain = org.vkimpact

# (str) Source code where the main.py lives
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,otf,json,db

# (list) List of directory to include (let empty to include all the files)
source.include_patterns = assets/*,assets/extra_styles/*,src/*

# (list) Source files to exclude (let empty to not exclude anything)
source.exclude_exts = spec,pyc,pyo,tmp,bak,md

# (list) List of directory to exclude (let empty to not exclude anything)
source.exclude_dirs = tests,bin,.pytest_cache,__pycache__,.git,.github,.venv,env,cache,.idea,.vscode

# (list) List of exclusions using pattern matching
# source.exclude_patterns = 

# (str) Application versioning (method 1)
version = 1.1

# (str) Application versioning (method 2)
# version.regex = __version__ = ['"](.*)['"]
# version.filename = %(source.dir)s/src/core/config.py

requirements = python3,kivy==2.3.0,https://github.com/kivymd/kivymd/archive/master.zip,materialyoucolor,materialshapes,asynckivy,asyncgui,aiohttp,multidict,yarl,frozenlist,aiosignal,attrs,async-timeout,charset-normalizer,propcache,aiosqlite,httpx,httpcore,anyio,h11,sniffio,beautifulsoup4,soupsieve,pydantic,cryptography,pillow,plyer,certifi,openssl,sqlite3

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivymd = ../../kivymd

# (list) Garden requirements
# garden_requirements =

# (str) Presplash of the application
# presplash.filename = %(source.dir)s/assets/presplash.png

# (str) Icon of the application
# icon.filename = %(source.dir)s/assets/icon.png

# (list) Supported orientations
# Valid values: landscape, sensorLandscape, portrait or all
orientation = portrait

# (list) List of service to declare
# services = NAME:ENTRYPOINT_TO_PY,NAME2:ENTRYPOINT2_TO_PY

#
# OSX Specific
#

#
# author = © Copyright Info

# change the major version of python used by the app
osx.python_version = 3

# Kivy version to use
osx.kivy_version = 2.3.0

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen
fullscreen = 0

# (string) Presplash background color (for android toolchain)
# Supported formats are: #RRGGBB #AARRGGBB or one of the color names
android.presplash_color = #1E2024

# (string) Presplash animation using Lottie format
# android.presplash_lottie = ""

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,VIBRATE,WAKE_LOCK

# (list) features (adds uses-feature to manifest)
# android.features = 

# (int) Target Android API, should be as high as possible.
android.api = 34

# (int) Minimum API your APK / AAB will support.
android.minapi = 24

# (int) Android SDK version to use
# android.sdk = 34

# (str) Android NDK version to use
android.ndk = 25b

# (int) Android NDK API to use. This is the minimum API your app will support, it should usually match android.minapi.
android.ndk_api = 24

# (bool) Use --private data storage (True) or --dir public storage (False)
android.private_storage = True

# (str) Android NDK directory (if empty, it will be automatically downloaded.)
# android.ndk_path =

# (str) Android SDK directory (if empty, it will be automatically downloaded.)
# android.sdk_path =

# (str) ANT directory (if empty, it will be automatically downloaded.)
# android.ant_path =

# (bool) If True, then skip trying to update the Android sdk
# This can be useful to avoid excess Internet downloads or save time
# when an update is due and you just want to test/build your package
android.skip_update = False

# (bool) If True, then automatically accept SDK license
# agreements. This is intended for automation only. If set to False,
# the default, you will be shown the license when building.
android.accept_sdk_license = True

# (str) Android entry point, default is ok for Kivy-based app
# android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements Android Activity
# android.activity_class_name = org.kivy.android.PythonActivity

# (list) Pattern to whitelist for the whole project
# android.whitelist =

# (str) Path to a custom whitelist file
# android.whitelist_src =

# (str) Path to a custom blacklist file
# android.blacklist_src =

# (list) List of Java .jar files to add to the libs so that pyjnius can access
# their classes. Don't add jars that you do not need, since extra jars can slow
# down the build process.
# android.add_jars =

# (list) List of Java files to add to the android project (can be java or a
# directory containing the files)
# android.add_src =

# (list) Android AAR archives to add
# android.add_aars =

# (list) Gradle dependencies
# android.gradle_dependencies =

# (bool) Enable AndroidX support. Enable when any of the tools or libraries need it.
android.enable_androidx = True

# (list) packaging options to add to android build.gradle
# android.add_packaging_options =

# (list) Java classes to add as activities to the manifest.
# android.add_activities =

# (str) OUYA Console category. Should be one of GAME or APP
# If you leave this blank, OUYA support will not be enabled
# android.ouya.category =

# (str) Filename of OUYA Console icon. It must be a 732x412 png image.
# android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
# android.manifest.intent_filters =

# (str) launchMode to set for the main activity
# android.manifest.launch_mode = standard

# (list) Android additional libraries to copy into libs/armeabi
# android.add_libs_armeabi =

# (list) Android additional libraries to copy into libs/armeabi-v7a
# android.add_libs_armeabi_v7a =

# (list) Android additional libraries to copy into libs/arm64-v8a
# android.add_libs_arm64_v8a =

# (list) Android additional libraries to copy into libs/x86
# android.add_libs_x86 =

# (list) Android additional libraries to copy into libs/x86_64
# android.add_libs_x86_64 =

# (bool) Indicate whether the screen should stay on
# Don't forget to add the WAKE_LOCK permission if you set this to True
# android.wakelock = False

# (list) Android application meta-data to set (key=value format)
# android.meta_data =

# (list) Android library project to add (will be added in the
# project.properties automatically.)
# android.library_references =

# (list) Android shared libraries which will be added to AndroidManifest.xml using <uses-library> tag
# android.uses_library =

# (str) Android logcat filters to use
android.logcat_filters = *:S python:D

# (bool) Android logcat only show traces for activity
# android.logcat_pid_only = False

# (str) Android additional adb arguments
# android.adb_args = -H 192.168.0.1 -P 5037

# (bool) Copy library instead of making a libdir and symlinks
# android.copy_libs = 1

# (list) The Android architectures to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
# In past, was `android.arch` as string (default to armeabi-v7a)
android.archs = arm64-v8a, armeabi-v7a

# (int) overrides automatic versionCode computation (if unset, computed from version)
# android.numeric_version = 1

# (bool) Allow backup of user data (in AndroidManifest.xml)
android.allow_backup = True

# (str) The format used to package the app for release mode (aab or apk or aar).
android.release_artifact = aab

# (str) The format used to package the app for debug mode (apk or aab).
android.debug_artifact = apk

# (str) Window soft input mode (adjustResize / resize ensures keyboard does not overlap chat input)
android.window_softinput_mode = resize

#
# Python for android (p4a) specific
#

# (str) python-for-android URL to use for branch / clone
# p4a.url =

# (str) python-for-android fork / branch to use
# p4a.branch = v2024.01.21

# (str) python-for-android git clone directory (if empty, it will be automatically cloned from github)
p4a.source_dir = %(source.dir)s/.buildozer/android/platform/python-for-android

# (str) The directory in which python-for-android should look for your own build recipes (if any)
# p4a.local_recipes =

# (str) Filename to the hook for p4a
# p4a.hook =

# (str) Bootstrap to use for android builds
# p4a.bootstrap = sdl2

# (int) port number for p4a webserver to use for serving assets
# p4a.port = 5000

# (bool) Whether to clamp device user-scale
# p4a.clamp_user_scale = False


#
# iOS specific
#

# (str) Path to a custom kivy-ios folder
# ios.kivy_ios_dir = ../kivy-ios
# Alternately, specify the URL and branch of a git checkout:
ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master

# (str) Name of the Xcode project to generate
ios.project_name = vkimpact

# (list) Permissions for iOS (leave empty if no special permissions needed)
# ios.codesign.allowed = false

# (str) Name of the certificate to use for signing the debug assets
# ios.codesign.debug = "iPhone Developer: <firstname> <lastname> (<hexstring>)"

# (str) The development team to use for signing the debug assets
# ios.codesign.development_team.debug = <hexstring>

# (str) Name of the certificate to use for signing the release assets
# ios.codesign.release = "iPhone Distribution: <firstname> <lastname> (<hexstring>)"

# (str) The development team to use for signing the release assets
# ios.codesign.development_team.release = <hexstring>


[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

# (str) Path to build artifact storage, default is .buildozer
# build_dir = ./.buildozer

# (str) Path to build output (i.e. .apk, .aab, .ipa) storage
bin_dir = ./bin
