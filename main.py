# -*- coding: utf-8 -*-
"""Lanceur Jochat : affiche l'erreur à l'écran si l'application ne démarre pas."""
import traceback
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView


class ErreurApp(App):
    def __init__(self, texte, **kw):
        super().__init__(**kw)
        self.texte = texte

    def build(self):
        sv = ScrollView()
        lab = Label(text="JOCHAT - ERREUR DE DEMARRAGE\n"
                         "Fais une capture d'ecran de cette page.\n\n" + self.texte,
                    size_hint_y=None, halign="left", valign="top",
                    font_size="12sp", color=(1, 0.8, 0.8, 1), markup=False)
        lab.bind(width=lambda w, v: setattr(w, "text_size", (v - 20, None)))
        lab.bind(texture_size=lambda w, s: setattr(w, "height", s[1] + 40))
        sv.add_widget(lab)
        return sv


def lancer():
    try:
        from kivy.base import ExceptionHandler, ExceptionManager

        class Garde(ExceptionHandler):
            def handle_exception(self, inst):
                try:
                    import jochat_app
                    jochat_app.signaler("".join(traceback.format_exception(type(inst), inst, inst.__traceback__)))
                except Exception:
                    pass
                return ExceptionManager.PASS
        ExceptionManager.add_handler(Garde())
    except Exception:
        pass
    try:
        import jochat_app
        jochat_app.JochatAndroid().run()
    except Exception:
        ErreurApp(traceback.format_exc()).run()


if __name__ == "__main__":
    lancer()
