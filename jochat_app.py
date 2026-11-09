# -*- coding: utf-8 -*-
"""Jochat 0.3 - interface type WhatsApp (Android/PC). Protocole MQTT + Fernet identique à la version web."""
import base64, hashlib, io, json, os, queue, threading, time, unicodedata, uuid
from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as C
import paho.mqtt.client as mqtt
from fernet_pur import Fernet, pbkdf2
import extras

__version__ = "0.3.0"
URL_VERSION = "https://jyao9152.github.io/Jochat-android/version.json"
D = os.path.dirname(os.path.abspath(__file__))
FONT = "Inter"
try:
    LabelBase.register("Inter", os.path.join(D, "fonts", "Inter-Regular.otf"),
                       fn_bold=os.path.join(D, "fonts", "Inter-Bold.otf"))
except Exception:
    FONT = "Roboto"
VERT, VERT_CLAIR = "#008069", "#25D366"
ENVOYE, RECU, TEXTE, GRIS, BLEU_TICK = "#D9FDD3", "#FFFFFF", "#111B21", "#667781", "#53BDEB"
FONDS = [("Beige", "#EFEAE2"), ("Menthe", "#E1F0E8"), ("Ciel", "#E6E9F5"), ("Rose", "#F5E6E6")]
TAILLES = [("Petite", 0.9), ("Moyenne", 1.0), ("Grande", 1.2)]
SERVEUR, PORT = "broker.hivemq.com", 1883
COULEURS = ["#00A884", "#5E47DE", "#D6405E", "#E5A100", "#0085C7", "#8B5CF6", "#E0662C"]
EMOJIS = "😀 😂 🤣 😊 😍 🥰 😘 😎 🤔 😅 😉 😢 😭 😡 🥳 😴 🤗 🙄 😱 🤯 👍 👎 👏 🙌 🙏 💪 👋 🤝 ✌️ 👌 ❤️ 🧡 💛 💚 💙 💜 🖤 💔 🔥 ✨ 🎉 💯 ⭐ 🌹 🎂 🎁 ☕ 🍕 🍔 ⚽ 🎵 📸 🚀 🌍 ☀️ 🌙 🐱 🐶 🦁 🐼 🦄".split(" ")
PREFS = {"lu": True, "en_ligne": True, "ecrit": True, "vibre": True, "taille": 1, "fond": 0}
Window.softinput_mode = "below_target"

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()

def heure(ts):
    return time.strftime("%H:%M", time.localtime(ts))

def vt(v):
    try: return tuple(int(x) for x in str(v).split("."))
    except Exception: return (0,)

def emoji_png(ch):
    n = "-".join("%x" % ord(c) for c in ch if ord(c) != 0xFE0F)
    p = os.path.join(D, "emoji", n + ".png")
    return p if os.path.exists(p) else None

def L(text="", size=15, color=TEXTE, mode="one", **kw):
    """mode 'one' : une ligne, coupée par … si trop longue ; 'wrap' : retour à la ligne ; 'raw' : brut."""
    kw.setdefault("halign", "left"); kw.setdefault("valign", "middle")
    lab = Label(text=str(text), font_name=FONT, font_size="%ssp" % size, color=C(color), **kw)
    if mode == "one":
        lab.shorten = True; lab.shorten_from = "right"; lab.max_lines = 1
        lab.bind(size=lambda w, s: setattr(w, "text_size", s))
    elif mode == "wrap":
        lab.size_hint_y = None
        lab.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        lab.bind(texture_size=lambda w, s: setattr(w, "height", s[1] + dp(4)))
    return lab

class Fond(BoxLayout):
    def __init__(self, bg, rayon=0, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*C(bg)); self.r = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(rayon)])
        self.bind(pos=self.maj, size=self.maj)
    def maj(self, *_):
        self.r.pos, self.r.size = self.pos, self.size

class Avatar(Widget):
    def __init__(self, nom, taille=46, **kw):
        super().__init__(size_hint=(None, None), size=(dp(taille),) * 2, **kw)
        with self.canvas:
            Color(*C(COULEURS[sum(map(ord, nom)) % len(COULEURS)])); self.e = Ellipse(pos=self.pos, size=self.size)
        self.l = L(nom[:1].upper() or "?", taille * 0.42, "#FFFFFF", halign="center", bold=True)
        self.add_widget(self.l); self.bind(pos=self.maj, size=self.maj)
    def maj(self, *_):
        self.e.pos, self.e.size = self.pos, self.size; self.l.pos, self.l.size = self.pos, self.size

class Ticks(Widget):
    def __init__(self, st, **kw):
        super().__init__(size_hint=(None, None), size=(dp(18), dp(12)), **kw)
        self.st = st; self.bind(pos=self.dessiner); self.dessiner()
    def dessiner(self, *_):
        self.canvas.clear(); x, y = self.pos
        with self.canvas:
            Color(*C(BLEU_TICK if self.st >= 3 else GRIS))
            for dx in ([0] if self.st < 2 else [0, dp(5)]):
                Line(points=[x + dx + dp(1), y + dp(6), x + dx + dp(4), y + dp(2), x + dx + dp(10), y + dp(10)], width=dp(1.1))

class Ico(Button):
    """Bouton à icône dessinée (aucune police nécessaire)."""
    def __init__(self, kind, col="#FFFFFF", bg=None, **kw):
        kw.setdefault("size_hint", (None, 1))
        super().__init__(background_normal="", background_down="", background_color=(0, 0, 0, 0), **kw)
        self.kind, self.col, self.bg = kind, col, bg
        self.bind(pos=self.dessin, size=self.dessin); self.dessin()
    def dessin(self, *_):
        self.canvas.before.clear(); self.canvas.after.clear()
        x, y = self.center; d = min(self.size); u = d / 11.0
        if self.bg:
            with self.canvas.before:
                Color(*C(self.bg)); Ellipse(pos=(x - d / 2, y - d / 2), size=(d, d))
        with self.canvas.after:
            Color(*C(self.col)); w = dp(1.8); k = self.kind
            if k == "dots":
                for t in (-2.8, 0, 2.8): Ellipse(pos=(x - u * .6, y + t * u - u * .6), size=(u * 1.2, u * 1.2))
            elif k == "back":
                Line(points=[x + u * 1.6, y + u * 3.2, x - u * 1.8, y, x + u * 1.6, y - u * 3.2], width=w)
                Line(points=[x - u * 1.8, y, x + u * 3.4, y], width=w)
            elif k == "send":
                Triangle(points=[x - u * 2.8, y + u * 3.2, x - u * 2.8, y - u * 3.2, x + u * 3.6, y])
            elif k in ("play", "stop"):
                if k == "play": Triangle(points=[x - u * 2, y + u * 3, x - u * 2, y - u * 3, x + u * 3, y])
                else: Rectangle(pos=(x - u * 2.4, y - u * 2.4), size=(u * 4.8, u * 4.8))
            elif k == "mic":
                RoundedRectangle(pos=(x - u * 1.3, y - u * .4), size=(u * 2.6, u * 4.4), radius=[u * 1.3])
                Line(ellipse=(x - u * 2.6, y - u * 3, u * 5.2, u * 5.2, 90, 270), width=w)
                Line(points=[x, y - u * 3, x, y - u * 4.3], width=w)
            elif k == "img":
                Line(rectangle=(x - u * 3.6, y - u * 2.8, u * 7.2, u * 5.6), width=w)
                Line(points=[x - u * 3, y - u * 2, x - u * .8, y + u * .6, x + u * .6, y - u * 1, x + u * 1.6, y - u * .2, x + u * 3, y - u * 2], width=w)
            elif k == "smile":
                Line(circle=(x, y, u * 3.9), width=w)
                for t in (-1.5, 1.5): Ellipse(pos=(x + t * u - u * .5, y + u * .8), size=(u, u))
                Line(ellipse=(x - u * 2.1, y - u * 2.7, u * 4.2, u * 4, 90, 270), width=w)
            elif k == "x":
                Line(points=[x - u * 2.6, y + u * 2.6, x + u * 2.6, y - u * 2.6], width=w)
                Line(points=[x - u * 2.6, y - u * 2.6, x + u * 2.6, y + u * 2.6], width=w)
            elif k == "plus":
                Line(points=[x - u * 3, y, x + u * 3, y], width=dp(2.4)); Line(points=[x, y - u * 3, x, y + u * 3], width=dp(2.4))

class BImg(ButtonBehavior, Image):
    pass

class Bouton(Button):
    def __init__(self, texte, bg=VERT, fg="#FFFFFF", **kw):
        super().__init__(text=texte, font_name=FONT, background_normal="", background_down="",
                         background_color=C(bg), color=C(fg), **kw)

def ligne_tap(contenu, hauteur, fn):
    w = FloatLayout(size_hint_y=None, height=hauteur)
    contenu.size_hint = (1, 1); w.add_widget(contenu)
    t = Button(background_normal="", background_color=(0, 0, 0, 0), size_hint=(1, 1))
    t.bind(on_release=lambda *_: fn()); w.add_widget(t)
    return w

def signaler(txt):
    app = App.get_running_app()
    if app and getattr(app, "nb_err", 9) < 3:
        app.nb_err += 1
        Clock.schedule_once(lambda dt: app.msg("Petite erreur", txt[-600:], 380), 0)

class JochatAndroid(App):
    def build(self):
        self.title = "Jochat"; self.nb_err = 0
        self.data_file = os.path.join(self.user_data_dir, "jochat2.json")
        try:
            with open(self.data_file, "r", encoding="utf-8") as f: self.data = json.load(f)
        except Exception:
            self.data = {}
        self.data.setdefault("contacts", {}); self.data.setdefault("client", uuid.uuid4().hex)
        self.prefs = self.data.setdefault("prefs", {})
        for k, v in PREFS.items(): self.prefs.setdefault(k, v)
        self.cles, self.ecrit, self.vu, self.tex = {}, {}, {}, {}
        self.recus = queue.Queue()
        self.ouvert = self.client = None; self.connected = False; self.dernier_ecrit = 0
        self.rec_on = False; self.rec_file = None; self.rec_t0 = 0; self.joue = self.joue_btn = None
        self.onglet = "chats"
        self.root_box = BoxLayout(orientation="vertical")
        self.header = Fond(VERT, size_hint_y=None, height=dp(58), padding=[dp(14), dp(6)], spacing=dp(8))
        self.tabbar = Fond(VERT, size_hint_y=None, height=dp(44))
        self.tabs = {}
        for cle, nom in (("chats", "DISCUSSIONS"), ("reglages", "RÉGLAGES")):
            b = Button(text=nom, font_name=FONT, font_size="13sp", bold=True, background_normal="",
                       background_down="", background_color=(0, 0, 0, 0))
            b.bind(on_release=lambda _b, c=cle: self.aller(c)); self.tabs[cle] = b; self.tabbar.add_widget(b)
        self.body = BoxLayout()
        for w in (self.header, self.tabbar, self.body): self.root_box.add_widget(w)
        Window.bind(on_keyboard=self.touche)
        self.connecter(); self.aller("chats")
        Clock.schedule_interval(self.poll_messages, 0.25); Clock.schedule_interval(self.heartbeat, 1)
        Clock.schedule_once(self.ask_name_if_needed, 0.3)
        Clock.schedule_once(lambda dt: self.verifier_maj(True), 6)
        return self.root_box

    # ---------- outils ----------
    def msg(self, titre, texte, h=230, boutons=()):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        sv = ScrollView(); sv.add_widget(L(texte, 14, mode="wrap")); box.add_widget(sv)
        for t, fn in boutons:
            b = Bouton(t, size_hint_y=None, height=dp(46)); b.bind(on_release=lambda *_, f=fn: f()); box.add_widget(b)
        p = Popup(title=titre, title_font=FONT, content=box, size_hint=(0.9, None), height=dp(h), separator_color=C(VERT))
        p.open(); return p

    def confirmer(self, titre, texte, fn):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(L(texte, 14, mode="wrap"))
        ligne = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(10)); box.add_widget(ligne)
        p = Popup(title=titre, title_font=FONT, content=box, size_hint=(0.9, None), height=dp(240), separator_color=C(VERT))
        a = Bouton("Annuler", "#9AA5AB"); o = Bouton("Confirmer")
        a.bind(on_release=lambda *_: p.dismiss()); o.bind(on_release=lambda *_: (p.dismiss(), fn()))
        ligne.add_widget(a); ligne.add_widget(o); p.open()

    def touche(self, _w, key, *_):
        if key == 27:
            if self.ouvert: self.show_contacts(); return True
            if self.onglet == "reglages": self.aller("chats"); return True
        return False

    def maj_header(self, widgets):
        self.header.clear_widgets()
        for w in widgets: self.header.add_widget(w)

    def titre(self):
        self.maj_header([L("Jochat", 22, "#FFFFFF", bold=True)])

    def montre_tabs(self, oui):
        self.tabbar.height = dp(44) if oui else 0; self.tabbar.opacity = 1 if oui else 0; self.tabbar.disabled = not oui
        for c, b in self.tabs.items():
            b.color = C("#FFFFFF" if c == self.onglet else "#B2DFD6")
            b.canvas.after.clear()
            if c == self.onglet:
                with b.canvas.after:
                    Color(1, 1, 1, 1); Rectangle(pos=(b.x, b.y), size=(b.width, dp(3)))
        Clock.schedule_once(lambda dt: self.montre_tabs_trait(), 0.05)

    def montre_tabs_trait(self):
        for c, b in self.tabs.items():
            b.canvas.after.clear()
            if c == self.onglet and self.tabbar.height:
                with b.canvas.after:
                    Color(1, 1, 1, 1); Rectangle(pos=(b.x, b.y), size=(b.width, dp(3)))

    def aller(self, onglet):
        self.onglet = onglet
        (self.show_contacts if onglet == "chats" else self.show_reglages)()

    def fond(self):
        Window.clearcolor = C(FONDS[self.prefs["fond"] % len(FONDS)][1])

    # ---------- liste des discussions ----------
    def show_contacts(self):
        self.ouvert = None; self.onglet = "chats"; self.fond(); self.titre(); self.montre_tabs(True)
        self.body.clear_widgets()
        racine = FloatLayout()
        fond = Fond("#FFFFFF", orientation="vertical", size_hint=(1, 1))
        self.statut = L("Connecté" if self.connected else "Connexion…", 11, GRIS, size_hint_y=None, height=dp(22), padding=[dp(14), 0])
        fond.add_widget(self.statut)
        sv = ScrollView(); lst = BoxLayout(orientation="vertical", size_hint_y=None)
        lst.bind(minimum_height=lst.setter("height")); sv.add_widget(lst); fond.add_widget(sv)
        cs = sorted(self.data["contacts"].items(), key=lambda kv: (kv[1]["msgs"][-1]["ts"] if kv[1].get("msgs") else 0), reverse=True)
        if not cs:
            lst.add_widget(L("Aucune discussion.\nAppuie sur le bouton vert + pour commencer.", 14, GRIS, mode="wrap", halign="center", padding=[dp(20), dp(30)]))
        for cid, c in cs: lst.add_widget(self.ligne_contact(cid, c))
        racine.add_widget(fond)
        fab = Ico("plus", bg=VERT_CLAIR, size_hint=(None, None), size=(dp(58), dp(58)), pos_hint={"right": 0.95, "y": 0.03})
        fab.bind(on_release=lambda *_: self.popup_nouveau_contact()); racine.add_widget(fab)
        self.body.add_widget(racine)

    def apercu(self, m):
        k = m.get("kind", "txt")
        return {"img": "Photo", "voc": "Message vocal", "stk": "Sticker"}.get(k) or m.get("texte", "")

    def ligne_contact(self, cid, c):
        last = c["msgs"][-1] if c.get("msgs") else None
        ap = (("Vous : " if last.get("moi") else "") + self.apercu(last)) if last else "Nouvelle discussion"
        row = BoxLayout(padding=[dp(14), dp(8)], spacing=dp(14))
        row.add_widget(Avatar(c.get("nom", "?"), 52))
        info = BoxLayout(orientation="vertical", spacing=dp(2))
        haut, bas = BoxLayout(size_hint_y=0.5), BoxLayout(size_hint_y=0.5)
        haut.add_widget(L(c.get("nom", "Contact"), 16, bold=True, valign="bottom"))
        nl = c.get("non_lus", 0)
        if last: haut.add_widget(L(heure(last["ts"]), 11, VERT_CLAIR if nl else GRIS, size_hint_x=None, width=dp(44), halign="right", valign="bottom"))
        bas.add_widget(L(ap.replace("\n", " "), 13, GRIS, valign="top"))
        if nl:
            bd = Fond(VERT_CLAIR, 10, size_hint=(None, None), size=(dp(24), dp(20)))
            bd.add_widget(L(str(nl), 11, "#FFFFFF", halign="center", bold=True)); bas.add_widget(bd)
        info.add_widget(haut); info.add_widget(bas); row.add_widget(info)
        return ligne_tap(row, dp(72), lambda: self.open_chat(cid))

    # ---------- réglages ----------
    def show_reglages(self):
        self.ouvert = None; self.onglet = "reglages"; self.fond(); self.titre(); self.montre_tabs(True)
        self.body.clear_widgets()
        fond = Fond("#FFFFFF", orientation="vertical"); sv = ScrollView()
        col = BoxLayout(orientation="vertical", size_hint_y=None); col.bind(minimum_height=col.setter("height"))
        sv.add_widget(col); fond.add_widget(sv); self.body.add_widget(fond)
        def titre(t): col.add_widget(L(t, 12, VERT, bold=True, size_hint_y=None, height=dp(38), padding=[dp(16), dp(10), 0, 0]))
        def action(t, sous, fn):
            r = BoxLayout(orientation="vertical", padding=[dp(16), dp(6)])
            r.add_widget(L(t, 15)); r.add_widget(L(sous, 12, GRIS)); col.add_widget(ligne_tap(r, dp(60), fn))
        def bascule(t, sous, cle):
            r = BoxLayout(padding=[dp(16), dp(6), dp(12), dp(6)], size_hint_y=None, height=dp(62), spacing=dp(8))
            tx = BoxLayout(orientation="vertical"); tx.add_widget(L(t, 15)); tx.add_widget(L(sous, 12, GRIS)); r.add_widget(tx)
            sw = Switch(active=self.prefs[cle], size_hint=(None, None), size=(dp(80), dp(40)), pos_hint={"center_y": .5})
            sw.bind(active=lambda _w, v: self.set_pref(cle, v)); r.add_widget(sw); col.add_widget(r)
        titre("PROFIL")
        action(self.data.get("nom", "?"), "Ton nom sert à retrouver tes discussions (non modifiable)", lambda: None)
        titre("CONFIDENTIALITÉ")
        bascule("Confirmations de lecture", "Si désactivé, les autres ne voient plus les coches bleues", "lu")
        bascule("Statut « en ligne »", "Si désactivé, tu apparais toujours hors ligne", "en_ligne")
        bascule("Indicateur « écrit… »", "Prévenir quand tu écris un message", "ecrit")
        titre("DISCUSSIONS")
        action("Taille du texte", TAILLES[self.prefs["taille"]][0] + " (touche pour changer)", self.cycle_taille)
        action("Fond d'écran", FONDS[self.prefs["fond"]][0] + " (touche pour changer)", self.cycle_fond)
        titre("NOTIFICATIONS")
        bascule("Vibration", "Vibrer à la réception d'un message", "vibre")
        titre("STOCKAGE")
        action("Vider les photos et vocaux", "Libère de la place, garde les textes", lambda: self.confirmer("Vider les médias", "Supprimer toutes les photos et tous les vocaux de cet appareil ?", self.vider_medias))
        action("Supprimer toutes les discussions", "Efface tout l'historique de cet appareil", lambda: self.confirmer("Tout supprimer", "Supprimer toutes tes discussions de cet appareil ? Action définitive.", self.tout_effacer))
        titre("AIDE")
        action("Rechercher une mise à jour", "Version installée : " + __version__, lambda: self.verifier_maj(False))
        action("À propos de Jochat", "Messagerie chiffrée par code secret", lambda: self.msg("Jochat " + __version__, "Messages chiffrés de bout en bout avec le code secret que tu partages avec ton contact.\n\nFonctionne avec la version web et PC de Jochat.", 300))

    def set_pref(self, k, v):
        self.prefs[k] = v; self.save_data()

    def cycle_taille(self):
        self.prefs["taille"] = (self.prefs["taille"] + 1) % len(TAILLES); self.save_data(); self.show_reglages()

    def cycle_fond(self):
        self.prefs["fond"] = (self.prefs["fond"] + 1) % len(FONDS); self.save_data(); self.show_reglages()

    def vider_medias(self):
        for c in self.data["contacts"].values():
            for m in c.get("msgs", []):
                if m.get("kind") in ("img", "voc"): m["data"] = None
        self.tex.clear(); self.save_data(); self.msg("Fait", "Photos et vocaux supprimés.", 180)

    def tout_effacer(self):
        for c in self.data["contacts"].values(): c["msgs"] = []; c["non_lus"] = 0
        self.tex.clear(); self.save_data(); self.msg("Fait", "Discussions supprimées.", 180)

    # ---------- mises à jour ----------
    def verifier_maj(self, silencieux):
        def tache():
            try:
                info = json.loads(extras.http_get(URL_VERSION))
                Clock.schedule_once(lambda dt: self.res_maj(info, silencieux), 0)
            except Exception as e:
                if not silencieux: Clock.schedule_once(lambda dt: self.msg("Mise à jour", "Impossible de vérifier (connexion internet ?).", 200), 0)
        threading.Thread(target=tache, daemon=True).start()

    def res_maj(self, info, silencieux):
        if vt(info.get("version")) > vt(__version__):
            self.msg("Mise à jour disponible", "Nouvelle version %s (tu as la %s).\n\n%s" % (info.get("version"), __version__, info.get("notes", "")), 360,
                     [("Télécharger", lambda: extras.ouvrir_url(info.get("apk", "")))])
        elif not silencieux:
            self.msg("À jour", "Tu as déjà la dernière version (%s)." % __version__, 190)

    # ---------- discussion ----------
    def open_chat(self, cid):
        self.ouvert = cid; self.fond(); self.montre_tabs(False)
        c = self.data["contacts"][cid]; c["non_lus"] = 0
        retour = Ico("back", width=dp(36)); retour.bind(on_release=lambda *_: self.show_contacts())
        t = BoxLayout(orientation="vertical")
        self.t_nom = L(c["nom"], 16, "#FFFFFF", bold=True, valign="bottom")
        self.t_stat = L(self.status_for(cid), 11, "#D1F4EA", valign="top")
        t.add_widget(self.t_nom); t.add_widget(self.t_stat)
        self.maj_header([retour, Avatar(c["nom"], 38), t])
        self.body.clear_widgets()
        panel = BoxLayout(orientation="vertical")
        self.msgs_sv = ScrollView()
        self.msgs_box = BoxLayout(orientation="vertical", size_hint_y=None, padding=[0, dp(8)], spacing=dp(1))
        self.msgs_box.bind(minimum_height=self.msgs_box.setter("height"))
        self.msgs_sv.add_widget(self.msgs_box); panel.add_widget(self.msgs_sv)
        self.panneau = BoxLayout(size_hint_y=None, height=0); panel.add_widget(self.panneau)
        barre = BoxLayout(size_hint_y=None, height=dp(58), padding=[dp(6), dp(6)], spacing=dp(6))
        pill = Fond("#FFFFFF", 22, padding=[dp(4), 0, dp(4), 0])
        smile = Ico("smile", GRIS, width=dp(38)); smile.bind(on_release=lambda *_: self.toggle_panneau())
        self.champ = TextInput(hint_text="Message", multiline=False, font_name=FONT, font_size="16sp", background_normal="",
                               background_active="", background_color=(0, 0, 0, 0), foreground_color=C(TEXTE),
                               cursor_color=C(VERT), padding=[dp(6), dp(14), dp(6), 0])
        self.champ.bind(on_text_validate=lambda *_: self.envoyer_msg(), text=self.on_texte)
        photo = Ico("img", GRIS, width=dp(38)); photo.bind(on_release=lambda *_: self.choisir_photo())
        for w in (smile, self.champ, photo): pill.add_widget(w)
        barre.add_widget(pill)
        self.b_annule = Ico("x", "#E53935", width=0, opacity=0, disabled=True); self.b_annule.bind(on_release=lambda *_: self.fin_rec(False))
        barre.add_widget(self.b_annule)
        self.bs = Ico("mic", bg=VERT, width=dp(46)); self.bs.bind(on_release=lambda *_: self.action_bs())
        barre.add_widget(self.bs); panel.add_widget(barre); self.body.add_widget(panel)
        self.render_messages(); self.save_data(); self.send_packet(cid, t="lu")

    def on_texte(self, *_):
        self.bs.kind = "send" if self.champ.text.strip() else "mic"; self.bs.dessin()
        if self.ouvert and time.time() - self.dernier_ecrit > 3:
            self.dernier_ecrit = time.time(); self.send_packet(self.ouvert, t="ecrit")

    def action_bs(self):
        if self.rec_on: self.fin_rec(True)
        elif self.champ.text.strip(): self.envoyer_msg()
        else: self.tap_micro()

    def toggle_panneau(self):
        if self.panneau.height:
            self.panneau.clear_widgets(); self.panneau.height = 0; return
        sv = ScrollView(); g = GridLayout(cols=6, size_hint_y=None, padding=dp(8), spacing=dp(4), row_default_height=dp(52), row_force_default=True)
        g.bind(minimum_height=g.setter("height"))
        for e in EMOJIS:
            p = emoji_png(e)
            if p:
                b = BImg(source=p); b.bind(on_release=lambda _b, ch=e: self.envoyer_media("stk", ch)); g.add_widget(b)
        sv.add_widget(g); self.panneau.add_widget(Fond("#F0F2F5", orientation="vertical")); self.panneau.children[0].add_widget(sv)
        self.panneau.height = dp(230)

    def render_messages(self):
        if not self.ouvert: return
        self.msgs_box.clear_widgets(); maxw = Window.width * 0.78; jour = None
        for m in self.data["contacts"][self.ouvert].get("msgs", []):
            j = time.strftime("%d/%m/%Y", time.localtime(m.get("ts", 0)))
            if j != jour:
                jour = j; puce = Fond("#FFFFFF", 7, size_hint=(None, None), size=(dp(110), dp(24)))
                puce.add_widget(L(j, 11, GRIS, halign="center"))
                r = BoxLayout(size_hint_y=None, height=dp(34), padding=[0, dp(5)])
                r.add_widget(Widget()); r.add_widget(puce); r.add_widget(Widget()); self.msgs_box.add_widget(r)
            try: self.msgs_box.add_widget(self.bulle(m, maxw))
            except Exception as e: signaler(str(e))
        Clock.schedule_once(lambda *_: setattr(self.msgs_sv, "scroll_y", 0), 0.05)

    def meta(self, m, moi):
        r = BoxLayout(size_hint=(1, None), height=dp(14), spacing=dp(3)); r.add_widget(Widget())
        r.add_widget(L(heure(m.get("ts", time.time())), 10, GRIS, size_hint=(None, 1), width=dp(34), halign="right"))
        if moi: r.add_widget(Ticks(m.get("st", 1)))
        return r

    def rangee(self, b, moi, extra=dp(3)):
        row = BoxLayout(size_hint_y=None, height=b.height + extra, padding=[dp(8), 0])
        if moi: row.add_widget(Widget()); row.add_widget(b)
        else: row.add_widget(b); row.add_widget(Widget())
        return row

    def texture(self, m):
        if m["id"] not in self.tex:
            raw = base64.b64decode(m["data"].split(",", 1)[1])
            self.tex[m["id"]] = CoreImage(io.BytesIO(raw), ext="jpg").texture
        return self.tex[m["id"]]

    def bulle(self, m, maxw):
        moi = m.get("moi"); k = m.get("kind", "txt"); pad = dp(8)
        if k == "stk":
            p = emoji_png(m.get("data", ""))
            b = BoxLayout(orientation="vertical", size_hint=(None, None), size=(dp(100), dp(112)))
            b.add_widget(Image(source=p) if p else L(m.get("data", ""), 40, halign="center")); b.add_widget(self.meta(m, moi))
            return self.rangee(b, moi)
        if k == "img" and m.get("data"):
            tx = self.texture(m); w = min(maxw, dp(240)); h = w * tx.height / float(tx.width)
            if h > dp(320): h = dp(320); w = h * tx.width / float(tx.height)
            b = Fond(ENVOYE if moi else RECU, 9, orientation="vertical", size_hint=(None, None), size=(w + 2 * pad, h + dp(18) + 2 * pad), padding=pad, spacing=dp(2))
            b.add_widget(Image(texture=tx, size_hint=(1, 1))); b.add_widget(self.meta(m, moi))
            return self.rangee(b, moi)
        if k in ("img", "voc"):
            b = Fond(ENVOYE if moi else RECU, 9, orientation="vertical", size_hint=(None, None), padding=pad, spacing=dp(2))
            if k == "voc" and m.get("data"):
                b.size = (dp(220) + 2 * pad, dp(44) + dp(18) + 2 * pad)
                r = BoxLayout(spacing=dp(8)); pl = Ico("play", "#FFFFFF", bg=VERT, width=dp(44))
                pl.bind(on_release=lambda btn, mm=m: self.toggle_play(mm, btn)); r.add_widget(pl)
                d = int(m.get("dur") or 0); r.add_widget(L("Vocal  %d:%02d" % (d // 60, d % 60), 14)); b.add_widget(r)
            else:
                b.size = (dp(190), dp(22) + dp(18) + 2 * pad); b.add_widget(L("Média expiré", 13, GRIS))
            b.add_widget(self.meta(m, moi)); return self.rangee(b, moi)
        lab = L(m.get("texte", ""), 15 * TAILLES[self.prefs["taille"]][1], mode="raw", size_hint=(None, None), valign="top")
        lab.texture_update(); w, h = lab.texture_size
        if w > maxw:
            lab.text_size = (maxw, None); lab.texture_update(); w, h = maxw, lab.texture_size[1]
        lab.text_size = (w, None); lab.size = (w, h)
        iw = max(w, dp(46) + (dp(24) if moi else 0))
        b = Fond(ENVOYE if moi else RECU, 9, orientation="vertical", size_hint=(None, None), size=(iw + 2 * pad, h + dp(18) + 2 * pad - dp(2)), padding=[pad, pad - dp(2)], spacing=dp(1))
        b.add_widget(lab); b.add_widget(self.meta(m, moi)); return self.rangee(b, moi)

    # ---------- vocaux ----------
    def tap_micro(self):
        if not extras.ANDROID: self.msg("Vocaux", "Les messages vocaux fonctionnent sur l'appli Android.", 200); return
        try:
            extras.permission_micro(lambda ok: self.debut_rec() if ok else self.msg("Micro", "Autorise le micro dans les réglages du téléphone pour envoyer des vocaux.", 220))
        except Exception as e: self.msg("Micro", "Erreur : " + str(e)[:150], 220)

    def debut_rec(self):
        try:
            self.rec_file = extras.rec_start(self.user_data_dir)
        except Exception as e:
            self.msg("Micro", "Impossible de démarrer : " + str(e)[:150], 220); return
        self.rec_on = True; self.rec_t0 = time.time(); self.bs.kind = "send"; self.bs.dessin()
        self.b_annule.width = dp(40); self.b_annule.opacity = 1; self.b_annule.disabled = False
        self.champ.disabled = True; self.champ.hint_text = "Enregistrement…  0 s"
        Clock.schedule_interval(self.tic_rec, 0.5)

    def tic_rec(self, _dt):
        if not self.rec_on: return False
        s = int(time.time() - self.rec_t0); self.champ.hint_text = "Enregistrement…  %d s" % s
        if s >= 30: self.fin_rec(True); return False

    def fin_rec(self, envoyer):
        if not self.rec_on: return
        self.rec_on = False; dur = int(time.time() - self.rec_t0)
        try: raw = extras.rec_stop(self.rec_file, envoyer and dur >= 1)
        except Exception: raw = None
        self.b_annule.width = 0; self.b_annule.opacity = 0; self.b_annule.disabled = True
        self.champ.disabled = False; self.champ.hint_text = "Message"; self.on_texte()
        if envoyer and raw: self.envoyer_media("voc", "data:audio/mp4;base64," + base64.b64encode(raw).decode(), dur)

    def toggle_play(self, m, btn):
        if self.joue == m["id"]:
            extras.stop_lecture(); self.joue = None; btn.kind = "play"; btn.dessin(); return
        if self.joue_btn: self.joue_btn.kind = "play"; self.joue_btn.dessin()
        try:
            head, b64 = m["data"].split(",", 1)
            ext = ".m4a" if ("mp4" in head or "aac" in head) else ".webm" if "webm" in head else ".ogg" if "ogg" in head else ".bin"
            extras.lecture(base64.b64decode(b64), ext, self.user_data_dir)
        except Exception as e:
            self.msg("Vocal", "Lecture impossible : " + str(e)[:150], 220); return
        self.joue, self.joue_btn = m["id"], btn; btn.kind = "stop"; btn.dessin()
        Clock.unschedule(self.veille); Clock.schedule_interval(self.veille, 0.5)

    def veille(self, _dt):
        if extras.en_lecture(): return True
        if self.joue_btn: self.joue_btn.kind = "play"; self.joue_btn.dessin()
        self.joue = self.joue_btn = None; return False

    # ---------- photos ----------
    def choisir_photo(self):
        if not extras.ANDROID: self.msg("Photos", "L'envoi de photos fonctionne sur l'appli Android.", 200); return
        try: extras.choisir_image(lambda u: self.envoyer_media("img", u), lambda e: self.msg("Photo", "Impossible : " + e[:150], 220))
        except Exception as e: self.msg("Photo", "Erreur : " + str(e)[:150], 220)

    def envoyer_media(self, kind, data, dur=0):
        if not self.ouvert: return
        m = {"id": uuid.uuid4().hex[:10], "moi": True, "kind": kind, "data": data, "dur": dur, "ts": time.time(), "st": 1}
        self.data["contacts"][self.ouvert]["msgs"].append(m); self.save_data(); self.render_messages()
        threading.Thread(target=self.send_packet, args=(self.ouvert,), kwargs=dict(t="med", id=m["id"], kind=kind, data=data, dur=dur, ts=m["ts"]), daemon=True).start()

    # ---------- nouveau contact / profil ----------
    def ask_name_if_needed(self, *_):
        if self.data.get("nom"): return
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        inp = TextInput(hint_text="Ton prénom", multiline=False, font_name=FONT, size_hint_y=None, height=dp(48), font_size="18sp")
        btn = Bouton("Continuer", size_hint_y=None, height=dp(46))
        box.add_widget(L("Bienvenue sur Jochat", 16)); box.add_widget(inp); box.add_widget(btn)
        p = Popup(title="Ton profil", title_font=FONT, content=box, size_hint=(0.9, None), height=dp(250), separator_color=C(VERT), auto_dismiss=False); p.open()
        def ok(*_):
            if inp.text.strip(): self.data["nom"] = inp.text.strip(); self.save_data(); p.dismiss()
        btn.bind(on_release=ok)

    def popup_nouveau_contact(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        nom = TextInput(hint_text="Prénom du contact", multiline=False, font_name=FONT, size_hint_y=None, height=dp(46))
        code = TextInput(hint_text="Code secret partagé", multiline=False, password=True, font_name=FONT, size_hint_y=None, height=dp(46))
        btn = Bouton("Créer la discussion", size_hint_y=None, height=dp(46))
        box.add_widget(L("Le même code secret doit être utilisé des deux côtés.", 12, GRIS, mode="wrap"))
        for w in (nom, code, btn): box.add_widget(w)
        p = Popup(title="Nouvelle discussion", title_font=FONT, content=box, size_hint=(0.9, None), height=dp(320), separator_color=C(VERT)); p.open()
        def creer(*_):
            ami, cd = nom.text.strip(), code.text
            if not ami or not cd: return
            cid = hashlib.sha256((",".join(sorted([norm(self.data["nom"]), norm(ami)])) + "|" + cd).encode()).hexdigest()[:24]
            if cid not in self.data["contacts"]:
                self.data["contacts"][cid] = {"nom": ami, "code": cd, "msgs": [], "non_lus": 0}
                if self.client:
                    try: self.client.subscribe("jochat2/" + cid, qos=1)
                    except Exception: pass
                self.save_data()
            p.dismiss(); self.open_chat(cid)
        btn.bind(on_release=creer)

    # ---------- protocole ----------
    def send_packet(self, cid, **packet):
        if not self.client: return
        t = packet.get("t")
        if (t == "lu" and not self.prefs["lu"]) or (t == "ping" and not self.prefs["en_ligne"]) or (t == "ecrit" and not self.prefs["ecrit"]): return
        try:
            packet["de"] = norm(self.data.get("nom", ""))
            self.client.publish("jochat2/" + cid, self.key_for(cid).encrypt(json.dumps(packet).encode()), qos=1)
        except Exception: pass

    def key_for(self, cid):
        if cid not in self.cles:
            self.cles[cid] = Fernet(base64.urlsafe_b64encode(pbkdf2(self.data["contacts"][cid]["code"].encode(), b"jochat2", 100_000, 32)))
        return self.cles[cid]

    def envoyer_msg(self):
        t = self.champ.text.strip() if self.ouvert else ""
        if not t: return
        m = {"id": uuid.uuid4().hex[:10], "moi": True, "texte": t[:2000], "ts": time.time(), "st": 1}
        self.data["contacts"][self.ouvert]["msgs"].append(m)
        self.send_packet(self.ouvert, t="msg", id=m["id"], texte=m["texte"], ts=m["ts"])
        self.champ.text = ""; self.champ.focus = True; self.save_data(); self.render_messages()

    def connecter(self):
        try:
            try: self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="jochat-" + self.data["client"], clean_session=False)
            except AttributeError: self.client = mqtt.Client(client_id="jochat-" + self.data["client"], clean_session=False)
            self.client.on_connect, self.client.on_message, self.client.on_disconnect = self.on_connect, self.on_message, self.on_disconnect
            self.client.connect_async(SERVEUR, PORT, 60); self.client.loop_start()
        except Exception: pass

    def on_connect(self, client, userdata, flags, rc, properties=None):
        self.connected = True
        for cid in list(self.data["contacts"]): client.subscribe("jochat2/" + cid, qos=1)
        self.ping_all()

    def on_disconnect(self, client, userdata, *a):
        self.connected = False

    def on_message(self, client, userdata, msg):
        try:
            cid = msg.topic.split("/", 1)[1]; self.recus.put((cid, json.loads(self.key_for(cid).decrypt(msg.payload))))
        except Exception: pass

    def ping_all(self):
        for cid in list(self.data["contacts"]): self.send_packet(cid, t="ping")

    def heartbeat(self, _dt):
        if self.connected and int(time.time()) % 20 == 0: self.ping_all()
        if self.ouvert and hasattr(self, "t_stat"): self.t_stat.text = self.status_for(self.ouvert)
        if self.onglet == "chats" and not self.ouvert and hasattr(self, "statut"): self.statut.text = "Connecté" if self.connected else "Connexion…"

    def status_for(self, cid):
        now = time.time()
        if now - self.ecrit.get(cid, 0) < 4: return "en train d'écrire…"
        return "en ligne" if now - self.vu.get(cid, 0) < 50 else "hors ligne"

    def poll_messages(self, _dt):
        changed = False
        while not self.recus.empty():
            try: self.process_packet(*self.recus.get_nowait()); changed = True
            except queue.Empty: break
        if changed:
            if self.ouvert: self.render_messages()
            elif self.onglet == "chats": self.show_contacts()

    def nouveau(self, cid, c, m):
        c["msgs"].append(m); self.send_packet(cid, t="recu", id=m["id"])
        if cid == self.ouvert: self.send_packet(cid, t="lu")
        else: c["non_lus"] = c.get("non_lus", 0) + 1
        if self.prefs["vibre"]: extras.vibrer(150)

    def process_packet(self, cid, p):
        c = self.data["contacts"].get(cid)
        if not c or p.get("de") == norm(self.data.get("nom", "")): return
        now, k = time.time(), p.get("t"); self.vu[cid] = now
        if k == "ecrit": self.ecrit[cid] = now
        elif k == "msg":
            if any(m.get("id") == p.get("id") for m in c["msgs"]): return
            self.nouveau(cid, c, {"id": p["id"], "moi": False, "texte": p["texte"], "ts": p["ts"], "st": 3})
        elif k == "med":
            if any(m.get("id") == p.get("id") for m in c["msgs"]): return
            self.nouveau(cid, c, {"id": p["id"], "moi": False, "kind": p.get("kind"), "data": p.get("data"), "dur": p.get("dur", 0), "ts": p["ts"], "st": 3})
        elif k == "recu":
            for m in c["msgs"]:
                if m.get("id") == p.get("id") and m.get("st", 1) < 2: m["st"] = 2
        elif k == "lu":
            for m in c["msgs"]:
                if m.get("moi"): m["st"] = 3
        if k in ("msg", "med", "recu", "lu"): self.save_data()

    def save_data(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, self.data_file)

    def on_pause(self): return True
    def on_stop(self):
        try:
            if self.client: self.client.disconnect(); self.client.loop_stop()
            extras.stop_lecture()
        except Exception: pass
        self.save_data()

if __name__ == "__main__":
    JochatAndroid().run()
