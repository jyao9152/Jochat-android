# -*- coding: utf-8 -*-
"""Jochat Android/PC - interface type WhatsApp, protocole MQTT+Fernet inchangé."""
import base64, hashlib, json, os, queue, time, unicodedata, uuid
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import get_color_from_hex as C
import paho.mqtt.client as mqtt
from cryptography.fernet import Fernet

D = os.path.dirname(os.path.abspath(__file__))
LabelBase.register("Inter", os.path.join(D, "fonts", "Inter-Regular.otf"),
                   bold=os.path.join(D, "fonts", "Inter-Bold.otf"))
VERT, VERT_FONCE, VERT_CLAIR = "#008069", "#075E54", "#25D366"
FOND, ENVOYE, RECU = "#EFEAE2", "#D9FDD3", "#FFFFFF"
TEXTE, GRIS, BLEU_TICK = "#111B21", "#667781", "#53BDEB"
SERVEUR, PORT = "broker.hivemq.com", 1883
COULEURS = ["#00A884", "#5E47DE", "#D6405E", "#E5A100", "#0085C7", "#8B5CF6", "#E0662C"]
Window.softinput_mode = "below_target"

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn").strip()

def heure(ts):
    return time.strftime("%H:%M", time.localtime(ts))

def L(text="", size=15, color=TEXTE, **kw):
    return Label(text=text, font_name="Inter", font_size=size if isinstance(size, str) else f"{size}sp",
                 color=C(color), markup=True, **kw)

class Avatar(Widget):
    def __init__(self, nom, taille=46, **kw):
        super().__init__(size_hint=(None, None), size=(dp(taille),) * 2, **kw)
        col = COULEURS[sum(map(ord, nom)) % len(COULEURS)]
        with self.canvas:
            Color(*C(col)); self.e = Ellipse(pos=self.pos, size=self.size)
        self.l = L(nom[:1].upper() or "?", size=taille * 0.42, color="#FFFFFF", bold=True)
        self.add_widget(self.l)
        self.bind(pos=self.maj, size=self.maj)
    def maj(self, *_):
        self.e.pos, self.e.size = self.pos, self.size
        self.l.pos, self.l.size = self.pos, self.size

class Fond(BoxLayout):
    """BoxLayout avec fond coloré (et coins arrondis optionnels)."""
    def __init__(self, bg, rayon=0, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*C(bg))
            self.r = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(rayon)])
        self.bind(pos=self.maj, size=self.maj)
    def maj(self, *_):
        self.r.pos, self.r.size = self.pos, self.size

class Ticks(Widget):
    """Coches dessinées (indépendantes de la police) : 1=envoyé, 2=reçu, 3=lu."""
    def __init__(self, st, **kw):
        super().__init__(size_hint=(None, None), size=(dp(18), dp(12)), **kw)
        self.st = st
        self.bind(pos=self.dessiner)
        self.dessiner()
    def dessiner(self, *_):
        self.canvas.clear()
        x, y = self.pos
        with self.canvas:
            Color(*C(BLEU_TICK if self.st >= 3 else GRIS))
            for dx in ([0] if self.st < 2 else [0, dp(5)]):
                Line(points=[x + dx + dp(1), y + dp(6), x + dx + dp(4), y + dp(2),
                             x + dx + dp(10), y + dp(10)], width=dp(1.1))

def bulle(m, maxw):
    moi = m.get("moi")
    lab = L(m.get("texte", ""), 15, size_hint=(None, None), halign="left", valign="top")
    lab.markup = False
    lab.texture_update()
    w, h = lab.texture_size
    if w > maxw:
        lab.text_size = (maxw, None); lab.texture_update(); w, h = maxw, lab.texture_size[1]
    lab.text_size = (w, None); lab.size = (w, h)
    meta_w = dp(46) + (dp(24) if moi else 0)
    iw = max(w, meta_w)
    pad = dp(8)
    b = Fond(ENVOYE if moi else RECU, 9, orientation="vertical", size_hint=(None, None),
             size=(iw + 2 * pad, h + dp(18) + 2 * pad - dp(2)), padding=[pad, pad - dp(2)], spacing=dp(1))
    b.add_widget(lab)
    meta = BoxLayout(size_hint=(1, None), height=dp(14), spacing=dp(3))
    meta.add_widget(Widget())
    meta.add_widget(L(heure(m.get("ts", time.time())), 10, GRIS, size_hint=(None, 1), width=dp(34)))
    if moi:
        meta.add_widget(Ticks(m.get("st", 1)))
    b.add_widget(meta)
    row = BoxLayout(size_hint_y=None, height=b.height + dp(3), padding=[dp(8), 0])
    if moi:
        row.add_widget(Widget()); row.add_widget(b)
    else:
        row.add_widget(b); row.add_widget(Widget())
    return row

class Bouton(Button):
    def __init__(self, texte, bg=VERT, fg="#FFFFFF", **kw):
        super().__init__(text=texte, font_name="Inter", background_normal="", background_down="",
                         background_color=C(bg), color=C(fg), **kw)

class JochatAndroid(App):
    def build(self):
        self.title = "Jochat"
        Window.clearcolor = C(FOND)
        self.data_file = os.path.join(self.user_data_dir, "jochat2.json")
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        self.data.setdefault("contacts", {}); self.data.setdefault("client", uuid.uuid4().hex)
        self.cles, self.ecrit, self.vu = {}, {}, {}
        self.recus = queue.Queue()
        self.ouvert, self.dernier_ecrit, self.client, self.connected = None, 0, None, False

        self.root_box = BoxLayout(orientation="vertical")
        self.header = Fond(VERT, size_hint_y=None, height=dp(58), padding=[dp(14), dp(6)], spacing=dp(10))
        self.root_box.add_widget(self.header)
        self.body = BoxLayout()
        self.root_box.add_widget(self.body)
        Window.bind(on_keyboard=self.touche)
        self.connecter()
        self.show_contacts()
        Clock.schedule_interval(self.poll_messages, 0.25)
        Clock.schedule_interval(self.heartbeat, 1)
        Clock.schedule_once(self.ask_name_if_needed, 0.3)
        return self.root_box

    # ---------- utilitaires ----------
    def popup(self, titre, contenu, h=230):
        p = Popup(title=titre, title_font="Inter", content=contenu, size_hint=(0.9, None),
                  height=dp(h), separator_color=C(VERT))
        p.open(); return p

    def touche(self, _w, key, *_):
        if key == 27 and self.ouvert:        # bouton retour Android
            self.show_contacts(); return True
        return False

    def maj_header(self, widgets):
        self.header.clear_widgets()
        for w in widgets: self.header.add_widget(w)

    # ---------- liste des discussions ----------
    def show_contacts(self):
        self.ouvert = None
        self.maj_header([L("Jochat", 22, "#FFFFFF", bold=True, halign="left", valign="middle")])
        self.header.children[0].bind(size=lambda w, s: setattr(w, "text_size", s))
        self.body.clear_widgets()
        racine = FloatLayout()
        fond = Fond("#FFFFFF", orientation="vertical", size_hint=(1, 1))
        self.statut = L(("Connecté" if self.connected else "Connexion…"), 11, GRIS,
                        size_hint_y=None, height=dp(22))
        fond.add_widget(self.statut)
        sv = ScrollView()
        lst = BoxLayout(orientation="vertical", size_hint_y=None)
        lst.bind(minimum_height=lst.setter("height"))
        sv.add_widget(lst); fond.add_widget(sv)
        cs = sorted(self.data["contacts"].items(),
                    key=lambda kv: (kv[1]["msgs"][-1]["ts"] if kv[1].get("msgs") else 0), reverse=True)
        if not cs:
            lst.add_widget(L("Aucune discussion.\nAppuie sur le bouton vert pour commencer.", 14, GRIS,
                             size_hint_y=None, height=dp(120), halign="center"))
        for cid, c in cs:
            lst.add_widget(self.ligne_contact(cid, c))
        racine.add_widget(fond)
        fab = Bouton("+", VERT_CLAIR, size_hint=(None, None), size=(dp(58), dp(58)),
                     pos_hint={"right": 0.95, "y": 0.03}, font_size="30sp")
        fab.bind(on_release=lambda *_: self.popup_nouveau_contact())
        racine.add_widget(fab)
        self.body.add_widget(racine)

    def ligne_contact(self, cid, c):
        last = c["msgs"][-1] if c.get("msgs") else None
        apercu = (("Vous : " if last.get("moi") else "") + last.get("texte", "")) if last else "Nouvelle discussion"
        row = BoxLayout(size_hint_y=None, height=dp(72), padding=[dp(14), dp(8)], spacing=dp(14))
        row.add_widget(Avatar(c.get("nom", "?"), 52))
        info = BoxLayout(orientation="vertical", spacing=dp(2))
        haut = BoxLayout(size_hint_y=0.5)
        n = L(c.get("nom", "Contact"), 16, bold=True, halign="left", valign="bottom")
        n.bind(size=lambda w, s: setattr(w, "text_size", s))
        haut.add_widget(n)
        nonlus = c.get("non_lus", 0)
        if last:
            h = L(heure(last["ts"]), 11, VERT_CLAIR if nonlus else GRIS, size_hint_x=None, width=dp(44),
                  halign="right", valign="bottom")
            h.bind(size=lambda w, s: setattr(w, "text_size", s)); haut.add_widget(h)
        bas = BoxLayout(size_hint_y=0.5)
        a = L(apercu[:60].replace("\n", " "), 13, GRIS, halign="left", valign="top")
        a.bind(size=lambda w, s: setattr(w, "text_size", s)); bas.add_widget(a)
        if nonlus:
            bas.add_widget(Fond(VERT_CLAIR, 10, size_hint=(None, None), size=(dp(22), dp(20)))); 
            bas.children[0].add_widget(L(str(nonlus), 11, "#FFFFFF", bold=True))
        info.add_widget(haut); info.add_widget(bas)
        row.add_widget(info)
        tap = Button(background_normal="", background_color=(0, 0, 0, 0), size_hint=(1, 1))
        tap.bind(on_release=lambda *_: self.open_chat(cid))
        wrap = FloatLayout(size_hint_y=None, height=dp(72))
        row.size_hint = (1, 1); wrap.add_widget(row); wrap.add_widget(tap)
        return wrap

    # ---------- discussion ----------
    def open_chat(self, cid):
        self.ouvert = cid
        c = self.data["contacts"][cid]; c["non_lus"] = 0
        retour = Bouton("<", VERT, size_hint=(None, 1), width=dp(34), font_size="24sp", bold=True)
        retour.bind(on_release=lambda *_: self.show_contacts())
        titre = BoxLayout(orientation="vertical")
        self.t_nom = L(c["nom"], 16, "#FFFFFF", bold=True, halign="left", valign="bottom")
        self.t_stat = L(self.status_for(cid), 11, "#D1F4EA", halign="left", valign="top")
        for t in (self.t_nom, self.t_stat):
            t.bind(size=lambda w, s: setattr(w, "text_size", s)); titre.add_widget(t)
        self.maj_header([retour, Avatar(c["nom"], 38), titre])
        self.body.clear_widgets()
        panel = BoxLayout(orientation="vertical")
        self.msgs_sv = ScrollView()
        self.msgs_box = BoxLayout(orientation="vertical", size_hint_y=None, padding=[0, dp(8)], spacing=dp(1))
        self.msgs_box.bind(minimum_height=self.msgs_box.setter("height"))
        self.msgs_sv.add_widget(self.msgs_box); panel.add_widget(self.msgs_sv)
        barre = BoxLayout(size_hint_y=None, height=dp(56), padding=[dp(6), dp(5)], spacing=dp(6))
        self.champ = TextInput(hint_text="Message", multiline=False, font_name="Inter", font_size="16sp",
                               background_normal="", background_active="", background_color=C("#FFFFFF"),
                               foreground_color=C(TEXTE), cursor_color=C(VERT), padding=[dp(16), dp(13)])
        self.champ.bind(on_text_validate=lambda *_: self.envoyer_msg(), text=self.on_typing)
        barre.add_widget(self.champ)
        env = Bouton(">", VERT, size_hint=(None, 1), width=dp(46), font_size="22sp", bold=True)
        env.bind(on_release=lambda *_: self.envoyer_msg())
        barre.add_widget(env)
        panel.add_widget(barre)
        self.body.add_widget(panel)
        self.render_messages(); self.save_data()
        self.send_packet(cid, t="lu")

    def render_messages(self):
        if not self.ouvert: return
        self.msgs_box.clear_widgets()
        maxw = Window.width * 0.78
        jour = None
        for m in self.data["contacts"][self.ouvert].get("msgs", []):
            j = time.strftime("%d/%m/%Y", time.localtime(m.get("ts", 0)))
            if j != jour:
                jour = j
                puce = Fond("#FFFFFFCC", 7, size_hint=(None, None), size=(dp(110), dp(24)))
                puce.add_widget(L(j, 11, GRIS))
                r = BoxLayout(size_hint_y=None, height=dp(34), padding=[0, dp(5)])
                r.add_widget(Widget()); r.add_widget(puce); r.add_widget(Widget())
                self.msgs_box.add_widget(r)
            self.msgs_box.add_widget(bulle(m, maxw))
        Clock.schedule_once(lambda *_: setattr(self.msgs_sv, "scroll_y", 0), 0.05)

    # ---------- nouveau contact / profil ----------
    def ask_name_if_needed(self, *_):
        if self.data.get("nom"): return
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        inp = TextInput(hint_text="Ton prénom", multiline=False, font_name="Inter",
                        size_hint_y=None, height=dp(48), font_size="18sp")
        btn = Bouton("Continuer", size_hint_y=None, height=dp(46))
        box.add_widget(L("Bienvenue sur Jochat", 16)); box.add_widget(inp); box.add_widget(btn)
        p = self.popup("Ton profil", box, 230); p.auto_dismiss = False
        def ok(*_):
            if inp.text.strip():
                self.data["nom"] = inp.text.strip(); self.save_data(); p.dismiss()
        btn.bind(on_release=ok)

    def popup_nouveau_contact(self):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        nom = TextInput(hint_text="Prénom du contact", multiline=False, font_name="Inter", size_hint_y=None, height=dp(46))
        code = TextInput(hint_text="Code secret partagé", multiline=False, password=True, font_name="Inter",
                         size_hint_y=None, height=dp(46))
        btn = Bouton("Créer la discussion", size_hint_y=None, height=dp(46))
        box.add_widget(L("Le même code secret doit être utilisé des deux côtés.", 12, GRIS))
        for w in (nom, code, btn): box.add_widget(w)
        p = self.popup("Nouvelle discussion", box, 290)
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

    def on_typing(self, *_):
        if self.ouvert and time.time() - self.dernier_ecrit > 3:
            self.dernier_ecrit = time.time(); self.send_packet(self.ouvert, t="ecrit")

    # ---------- protocole (inchangé) ----------
    def send_packet(self, cid, **packet):
        if not self.client: return
        try:
            packet["de"] = norm(self.data.get("nom", ""))
            self.client.publish("jochat2/" + cid, self.key_for(cid).encrypt(json.dumps(packet).encode()), qos=1)
        except Exception: pass

    def key_for(self, cid):
        if cid not in self.cles:
            raw = self.data["contacts"][cid]["code"].encode()
            self.cles[cid] = Fernet(base64.urlsafe_b64encode(hashlib.pbkdf2_hmac("sha256", raw, b"jochat2", 100_000)))
        return self.cles[cid]

    def envoyer_msg(self):
        t = self.champ.text.strip() if self.ouvert else ""
        if not t: return
        m = {"id": uuid.uuid4().hex[:10], "moi": True, "texte": t[:2000], "ts": time.time(), "st": 1}
        self.data["contacts"][self.ouvert]["msgs"].append(m)
        self.send_packet(self.ouvert, t="msg", id=m["id"], texte=m["texte"], ts=m["ts"])
        self.champ.text = ""; self.champ.focus = True
        self.save_data(); self.render_messages()

    def connecter(self):
        try:
            try:
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="jochat-" + self.data["client"], clean_session=False)
            except AttributeError:
                self.client = mqtt.Client(client_id="jochat-" + self.data["client"], clean_session=False)
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
            cid = msg.topic.split("/", 1)[1]
            self.recus.put((cid, json.loads(self.key_for(cid).decrypt(msg.payload))))
        except Exception: pass

    def ping_all(self):
        for cid in list(self.data["contacts"]): self.send_packet(cid, t="ping")

    def heartbeat(self, _dt):
        if self.connected and int(time.time()) % 20 == 0: self.ping_all()
        if self.ouvert and hasattr(self, "t_stat"): self.t_stat.text = self.status_for(self.ouvert)
        if not self.ouvert and hasattr(self, "statut"): self.statut.text = "Connecté" if self.connected else "Connexion…"

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
            else: self.show_contacts()

    def process_packet(self, cid, p):
        c = self.data["contacts"].get(cid)
        if not c or p.get("de") == norm(self.data.get("nom", "")): return
        now, k = time.time(), p.get("t")
        self.vu[cid] = now
        if k == "ecrit": self.ecrit[cid] = now
        elif k == "msg":
            if any(m.get("id") == p.get("id") for m in c["msgs"]): return
            c["msgs"].append({"id": p["id"], "moi": False, "texte": p["texte"], "ts": p["ts"], "st": 3})
            self.send_packet(cid, t="recu", id=p["id"])
            if cid == self.ouvert: self.send_packet(cid, t="lu")
            else: c["non_lus"] = c.get("non_lus", 0) + 1
        elif k == "recu":
            for m in c["msgs"]:
                if m.get("id") == p.get("id") and m.get("st", 1) < 2: m["st"] = 2
        elif k == "lu":
            for m in c["msgs"]:
                if m.get("moi"): m["st"] = 3
        if k in ("msg", "recu", "lu"): self.save_data()

    def save_data(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        tmp = self.data_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, self.data_file)

    def on_pause(self): return True
    def on_stop(self):
        try:
            if self.client: self.client.disconnect(); self.client.loop_stop()
        except Exception: pass
        self.save_data()

if __name__ == "__main__":
    JochatAndroid().run()
