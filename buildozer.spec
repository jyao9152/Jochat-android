[app]
title = Jochat
package.name = jochat
package.domain = ci.jochat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,otf,ttf
version = 0.2.0
requirements = python3,kivy,paho-mqtt,cryptography
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 35
android.minapi = 23
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
