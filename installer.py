#!/usr/bin/env python3

import gi
import subprocess
import sys
import os

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf

class TanukiInstaller(Gtk.Window):
    def __init__(self):
        super().__init__(title="Asistente de Instalación - Tanuki!")
        self.set_border_width(20)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.add(vbox)

        label = Gtk.Label(label="¿Deseas instalar todos los componentes necesarios en su sistema?")
        label.set_line_wrap(True)
        vbox.pack_start(label, True, True, 0)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(hbox, False, False, 0)

        btn_cancel = Gtk.Button(label="Cancelar")
        btn_cancel.connect("clicked", Gtk.main_quit)
        hbox.pack_start(btn_cancel, False, False, 0)

        btn_uninstall = Gtk.Button(label="Desinstalar")
        btn_uninstall.connect("clicked", self.on_uninstall)
        hbox.pack_start(btn_uninstall, False, False, 0)

        btn_continue = Gtk.Button(label="Continuar")
        btn_continue.get_style_context().add_class("suggested-action")
        btn_continue.connect("clicked", self.on_install)
        hbox.pack_start(btn_continue, False, False, 0)

        self.show_all()

    def run_pkexec(self, cmd_list):
        full_cmd = ["pkexec", "bash", "-c", " && ".join(cmd_list)]
        try:
            subprocess.run(full_cmd, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def on_install(self, btn):
        commands = [
            "apt update",
            "apt install -y python3-gi python3-psutil python3-pyclamd clamav-daemon zenity",
            "sed -i 's/User clamav/User root/g' /etc/clamav/clamd.conf",
            "systemctl restart clamav-daemon"
        ]
        if self.run_pkexec(commands):
            self.show_message("Éxito", "Componentes instalados y configurados correctamente.")
            Gtk.main_quit()
        else:
            self.show_message("Error", "No se pudo completar la instalación.")

    def on_uninstall(self, btn):
        commands = [
            "apt purge -y clamav-daemon python3-pyclamd",
            "apt autoremove -y"
        ]
        if self.run_pkexec(commands):
            self.show_message("Éxito", "Componentes eliminados del sistema.")
            Gtk.main_quit()
        else:
            self.show_message("Error", "No se pudo completar la desinstalación.")

    def show_message(self, title, text):
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO,
                                  buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

if __name__ == "__main__":
    app = TanukiInstaller()
    Gtk.main()