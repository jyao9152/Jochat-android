[app]
title = Jochat
package.name = jochat
package.domain = ci.jochat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,otf,ttf
source.exclude_dirs = web,.github,bin,venv
version = 0.3.0
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,paho-mqtt
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/icon.png
android.presplash_color = #FFFFFF

android.permissions = INTERNET,ACCESS_NETWORK_STATE,RECORD_AUDIO,VIBRATE
android.api = 34
android.ndk = 25b
android.minapi = 23
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
