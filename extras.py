# -*- coding: utf-8 -*-
"""Fonctions propres à Android (micro, galerie, vibration, réseau). Sans effet ailleurs."""
import base64, os, threading, time
from kivy.clock import Clock
ANDROID = False
try:
    from jnius import autoclass
    from android import activity
    ANDROID = True
except Exception:
    pass

def _act():
    return autoclass("org.kivy.android.PythonActivity").mActivity

def http_get(url, timeout=10):
    url += ("&" if "?" in url else "?") + "t=%d" % time.time()
    if ANDROID:
        c = autoclass("java.net.URL")(url).openConnection()
        c.setConnectTimeout(timeout * 1000); c.setReadTimeout(timeout * 1000); c.setUseCaches(False)
        s = autoclass("java.util.Scanner")(c.getInputStream(), "UTF-8").useDelimiter("\\A")
        return s.next() if s.hasNext() else ""
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")

def ouvrir_url(url):
    if ANDROID:
        I, U = autoclass("android.content.Intent"), autoclass("android.net.Uri")
        _act().startActivity(I(I.ACTION_VIEW, U.parse(url)))
    else:
        import webbrowser; webbrowser.open(url)

def vibrer(ms=150):
    if not ANDROID: return
    try:
        v = _act().getSystemService(autoclass("android.content.Context").VIBRATOR_SERVICE)
        v.vibrate(ms)
    except Exception:
        pass

def permission_micro(cb):
    from android.permissions import request_permissions, check_permission, Permission
    if check_permission(Permission.RECORD_AUDIO):
        cb(True); return
    request_permissions([Permission.RECORD_AUDIO],
                        lambda p, g: Clock.schedule_once(lambda dt: cb(bool(g) and all(g)), 0))

# ---- enregistrement / lecture ----
_mr = None; _mp = None
def rec_start(dossier):
    global _mr
    MR = autoclass("android.media.MediaRecorder")
    m = MR()
    m.setAudioSource(autoclass("android.media.MediaRecorder$AudioSource").MIC)
    m.setOutputFormat(autoclass("android.media.MediaRecorder$OutputFormat").MPEG_4)
    m.setAudioEncoder(autoclass("android.media.MediaRecorder$AudioEncoder").AAC)
    m.setAudioEncodingBitRate(24000); m.setAudioSamplingRate(16000)
    f = os.path.join(dossier, "rec.m4a")
    m.setOutputFile(f); m.prepare(); m.start(); _mr = m
    return f

def rec_stop(f, garder=True):
    global _mr
    m, _mr = _mr, None
    try: m.stop()
    except Exception: garder = False
    try: m.release()
    except Exception: pass
    return open(f, "rb").read() if garder and os.path.exists(f) else None

def lecture(raw, ext, dossier):
    global _mp
    stop_lecture()
    f = os.path.join(dossier, "lecture" + ext)
    open(f, "wb").write(raw)
    mp = autoclass("android.media.MediaPlayer")()
    mp.setDataSource(f); mp.prepare(); mp.start(); _mp = mp

def stop_lecture():
    global _mp
    mp, _mp = _mp, None
    if mp:
        try: mp.stop()
        except Exception: pass
        try: mp.release()
        except Exception: pass

def en_lecture():
    try: return bool(_mp and _mp.isPlaying())
    except Exception: return False

# ---- galerie : choisir une photo, la réduire, la renvoyer en data-URL JPEG ----
def _reduire(uri):
    cr = _act().getContentResolver()
    BF, Opt = autoclass("android.graphics.BitmapFactory"), autoclass("android.graphics.BitmapFactory$Options")
    o = Opt(); o.inJustDecodeBounds = True
    s = cr.openInputStream(uri); BF.decodeStream(s); s.close()
    ech, m = 1, max(o.outWidth, o.outHeight)
    while m // ech > 1600: ech *= 2
    o2 = Opt(); o2.inSampleSize = ech
    s = cr.openInputStream(uri); bmp = BF.decodeStream(s, None, o2); s.close()
    Bm = autoclass("android.graphics.Bitmap")
    w, h = bmp.getWidth(), bmp.getHeight()
    try:
        s = cr.openInputStream(uri)
        rot = {6: 90, 3: 180, 8: 270}.get(autoclass("android.media.ExifInterface")(s).getAttributeInt("Orientation", 1), 0)
        s.close()
        if rot:
            M = autoclass("android.graphics.Matrix")(); M.postRotate(float(rot))
            bmp = Bm.createBitmap(bmp, 0, 0, w, h, M, True); w, h = bmp.getWidth(), bmp.getHeight()
    except Exception:
        pass
    k = min(1.0, 720.0 / max(w, h))
    if k < 1: bmp = Bm.createScaledBitmap(bmp, int(w * k), int(h * k), True)
    BA, CF = autoclass("java.io.ByteArrayOutputStream"), autoclass("android.graphics.Bitmap$CompressFormat")
    q = 70
    while True:
        b = BA(); bmp.compress(CF.JPEG, q, b)
        data = bytes(bytearray([x & 0xFF for x in b.toByteArray()]))
        if len(data) < 90000 or q <= 30: break
        q -= 10
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()

def choisir_image(cb, erreur):
    I = autoclass("android.content.Intent")
    it = I(I.ACTION_GET_CONTENT); it.setType("image/*"); it.addCategory(I.CATEGORY_OPENABLE)
    def res(req, code, data):
        if req != 4242: return
        activity.unbind(on_activity_result=res)
        if code != -1 or data is None: return
        uri = data.getData()
        def tache():
            try:
                u = _reduire(uri); Clock.schedule_once(lambda dt: cb(u), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: erreur(str(e)), 0)
        threading.Thread(target=tache, daemon=True).start()
    activity.bind(on_activity_result=res)
    _act().startActivityForResult(it, 4242)
