import gi
import os
import subprocess
import psutil
import tempfile
import stat
import threading
import shutil

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango, Gdk, GdkPixbuf

try:
    import pyclamd
except ImportError:
    pyclamd = None

class AlecaishereApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Alecaishere Pro")
        self.set_default_size(900, 750)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.logo_path = os.path.join(self.base_path, "logo.png")
        
        self.quarantine_path = os.path.expanduser("~/.tanuki_quarantine")
        if not os.path.exists(self.quarantine_path):
            os.makedirs(self.quarantine_path)
        
        if os.path.exists(self.logo_path):
            self.set_icon_from_file(self.logo_path)

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.set_title("Tanuki!")
        headerbar.set_subtitle("Powered by ClamAV")
        self.set_titlebar(headerbar)

        self.add_header_button(headerbar, "riseup.png", "RiseupVPN", "riseup-vpn", "riseup-vpn")
        self.add_header_button(headerbar, "cryptomator.png", "Cryptomator", "cryptomator", "cryptomator")

        btn_about = Gtk.Button()
        btn_about.set_relief(Gtk.ReliefStyle.NONE)
        btn_about.set_image(Gtk.Image.new_from_icon_name("help-about", Gtk.IconSize.LARGE_TOOLBAR))
        btn_about.connect("clicked", self.show_about)
        headerbar.pack_end(btn_about)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(paned)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sidebar.set_size_request(240, -1)
        for m in ["top", "bottom", "start", "end"]: getattr(sidebar, f"set_margin_{m}")(12)
        
        sidebar_frame = Gtk.Frame()
        sidebar_frame.add(sidebar)
        paned.pack1(sidebar_frame, False, False)

        if os.path.exists(self.logo_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(self.logo_path, 224, 224, True)
            sidebar.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 10)

        sys_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in [8]: sys_box.set_margin_all(m) if hasattr(sys_box, 'set_margin_all') else [getattr(sys_box, f"set_margin_{x}")(m) for x in ["top","bottom","start","end"]]
        sys_frame = Gtk.Frame(label="Monitor del Sistema")
        sys_frame.add(sys_box)
        
        self.disk_label, self.ram_label, self.cpu_label = Gtk.Label(xalign=0), Gtk.Label(xalign=0), Gtk.Label(xalign=0)
        for lbl in [self.disk_label, self.ram_label, self.cpu_label]: sys_box.pack_start(lbl, False, False, 0)
        sidebar.pack_start(sys_frame, False, False, 0)
        
        self.update_system_info()
        GLib.timeout_add_seconds(2, self.update_system_info)

        scrolled = Gtk.ScrolledWindow()
        paned.pack2(scrolled, True, True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in [12]: content.set_margin_all(m) if hasattr(content, 'set_margin_all') else [getattr(content, f"set_margin_{x}")(m) for x in ["top","bottom","start","end"]]
        scrolled.add(content)

        self.add_protection_ui(content)

        self.add_section(content, "Mantenimiento General", [
            ("Limpiar APT (Caché)", "package-x-generic", True, "chk_apt"),
            ("Limpiar Logs Journal", "document-properties", True, "chk_journal"),
            ("Vaciar Temporales (/tmp)", "user-trash-full", True, "chk_tmp"),
        ])

        self.add_section(content, "Seguridad de Usuario (Home)", [
            ("Analizar Descargas", "folder-download", True, "scan_downloads"),
            ("Analizar Escritorio", "user-desktop", True, "scan_desktop"),
            ("Analizar Documentos", "folder-documents", False, "scan_docs"),
        ])
        
        self.add_section(content, "Rutas de Malware Comunes", [
            ("Analizar Caché (.cache)", "folder-temp", True, "scan_cache"),
            ("Analizar Extensiones (.config)", "preferences-desktop-peripherals", False, "scan_config"),
            ("Analizar Apps Locales (/usr/local/bin)", "system-software-install", True, "scan_usr_local"),
        ])

        self.text_view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text_view.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.05, 0.05, 0.05, 1))
        self.text_view.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 1, 0, 1))
        self.text_view.override_font(Pango.FontDescription("Monospace 9"))
        
        terminal_scroll = Gtk.ScrolledWindow(min_content_height=150)
        terminal_scroll.add(self.text_view)
        content.pack_start(terminal_scroll, True, True, 0)

        self.progress = Gtk.ProgressBar(show_text=True)
        content.pack_start(self.progress, False, False, 6)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_box.set_halign(Gtk.Align.END)
        
        btn_quarantine = Gtk.Button(label="Ver Cuarentena")
        btn_quarantine.set_image(Gtk.Image.new_from_icon_name("security-high", Gtk.IconSize.BUTTON))
        btn_quarantine.connect("clicked", lambda x: subprocess.run(['xdg-open', self.quarantine_path]))
        action_box.pack_start(btn_quarantine, False, False, 0)

        btn_custom = Gtk.Button(label="Analizar Carpeta...")
        btn_custom.set_image(Gtk.Image.new_from_icon_name("folder-open", Gtk.IconSize.BUTTON))
        btn_custom.connect("clicked", self.on_custom_scan)
        action_box.pack_start(btn_custom, False, False, 0)

        self.btn_run = Gtk.Button(label="Iniciar Mantenimiento")
        self.btn_run.get_style_context().add_class("suggested-action")
        self.btn_run.connect("clicked", self.start_cleaning)
        action_box.pack_start(self.btn_run, False, False, 0)
        
        content.pack_start(action_box, False, False, 0)

    def add_header_button(self, headerbar, icon_file, label, binary, package):
        icon_path = os.path.join(self.base_path, icon_file)
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_tooltip_text(f"Abrir {label}")
        if os.path.exists(icon_path):
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 24, 24, True)
            btn.set_image(Gtk.Image.new_from_pixbuf(pix))
        else: btn.set_label(label[0])
        btn.connect("clicked", self.on_external_app_clicked, label, binary, package)
        headerbar.pack_start(btn)

    def on_external_app_clicked(self, btn, label, binary, package):
        if shutil.which(binary):
            subprocess.Popen([binary])
        else:
            if package == "cryptomator":
                dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.ERROR,
                                          buttons=Gtk.ButtonsType.OK, text=f"{label} no está instalado")
                dialog.format_secondary_text(f"{label} debe instalarse manualmente desde su sitio oficial o repositorio.")
                dialog.run()
                dialog.destroy()
            else:
                dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                                          buttons=Gtk.ButtonsType.YES_NO, text=f"{label} no está instalado")
                dialog.format_secondary_text(f"¿Deseas instalar {label} ahora?")
                response = dialog.run()
                dialog.destroy()
                if response == Gtk.ResponseType.YES:
                    def install_worker():
                        self.log(f"--- INSTALANDO {label.upper()} ---")
                        cmd = f"apt update && apt install -y {package}"
                        proc = subprocess.Popen(["pkexec", "bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                        if proc.stdout:
                            for line in proc.stdout:
                                self.log(line.strip())
                        proc.wait()
                        self.log(f"--- FINALIZADO ---")
                    threading.Thread(target=install_worker, daemon=True).start()

    def add_protection_ui(self, container):
        frame = Gtk.Frame(label="Estado del Antivirus")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_all(10) if hasattr(box, 'set_margin_all') else [getattr(box, f"set_margin_{x}")(10) for x in ["top","bottom","start","end"]]
        lbl = Gtk.Label(label="Base de datos de virus:")
        box.pack_start(lbl, False, False, 0)
        self.btn_update = Gtk.Button(label="Actualizar Firmas")
        self.btn_update.get_style_context().add_class("flat")
        self.btn_update.connect("clicked", self.update_signatures)
        box.pack_end(self.btn_update, False, False, 0)
        frame.add(box)
        container.pack_start(frame, False, False, 0)

    def update_signatures(self, btn):
        btn.set_sensitive(False)
        self.log("Iniciando actualización de firmas (freshclam)...")
        def worker():
            proc = subprocess.Popen(["pkexec", "freshclam"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout: self.log(line.strip())
            proc.wait()
            GLib.idle_add(btn.set_sensitive, True)
            self.log("Actualización finalizada.")
        threading.Thread(target=worker, daemon=True).start()

    def move_to_quarantine(self, file_path):
        try:
            if not os.path.exists(file_path): return False
            name = os.path.basename(file_path)
            dest = os.path.join(self.quarantine_path, f"{name}.infected")
            shutil.move(file_path, dest)
            os.chmod(dest, 0o000)
            self.log(f"☣ AISLADO: {name} movido a cuarentena.")
            return True
        except Exception as e: 
            self.log(f"Error al aislar {file_path}: {e}")
            return False

    def add_section(self, container, title, items):
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in [8]: [getattr(box, f"set_margin_{x}")(m) for x in ["top","bottom","start","end"]]
        for label, icon, active, attr_name in items:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hbox.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            chk = Gtk.CheckButton(label=label, active=active)
            hbox.pack_start(chk, True, True, 0)
            box.pack_start(hbox, False, False, 0)
            setattr(self, attr_name, chk)
        frame.add(box)
        container.pack_start(frame, False, False, 0)

    def log(self, text):
        buf = self.text_view.get_buffer()
        GLib.idle_add(lambda: buf.insert(buf.get_end_iter(), f"» {text}\n"))
        adj = self.text_view.get_vadjustment()
        GLib.idle_add(lambda: adj.set_value(adj.get_upper() - adj.get_page_size()))

    def update_system_info(self):
        try:
            d, m = psutil.disk_usage('/'), psutil.virtual_memory()
            self.disk_label.set_markup(f"<b>Disco:</b> {d.free//10**9}GB libres")
            self.ram_label.set_markup(f"<b>RAM:</b> {m.percent}%")
            self.cpu_label.set_markup(f"<b>CPU:</b> {psutil.cpu_percent()}%")
        except: pass
        return True

    def run_clamav_logic(self, path):
        if not pyclamd or not os.path.exists(path): return
        try:
            cd = pyclamd.ClamdUnixSocket()
            if cd.ping():
                self.log(f"Analizando: {path}...")
                results = cd.multiscan_file(path)
                if results:
                    for f, r in results.items():
                        if "Permission denied" not in str(r):
                            self.log(f"¡PELIGRO! {r[1]} en {f}")
                            self.move_to_quarantine(f)
                else: self.log(f"✓ {path} limpio.")
        except Exception as e: self.log(f"Error en {path}: {e}")

    def on_custom_scan(self, btn):
        dlg = Gtk.FileChooserDialog(title="Seleccionar Carpeta", transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Analizar", Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            threading.Thread(target=self.run_clamav_logic, args=(path,), daemon=True).start()
        dlg.destroy()

    def start_cleaning(self, btn):
        self.btn_run.set_sensitive(False)
        self.text_view.get_buffer().set_text("")
        tasks = []
        if self.chk_apt.get_active(): tasks.append(("limpieza", "APT"))
        if self.chk_journal.get_active(): tasks.append(("limpieza", "Journal"))
        if self.chk_tmp.get_active(): tasks.append(("limpieza", "Temporales"))
        scan_map = {"scan_downloads": os.path.expanduser("~/Downloads"), "scan_desktop": os.path.expanduser("~/Desktop"), "scan_docs": os.path.expanduser("~/Documents"), "scan_cache": os.path.expanduser("~/.cache"), "scan_config": os.path.expanduser("~/.config"), "scan_usr_local": "/usr/local/bin"}
        for attr, path in scan_map.items():
            if hasattr(self, attr) and getattr(self, attr).get_active(): tasks.append(("scan", path))
        def worker():
            total = len(tasks)
            if total == 0: GLib.idle_add(self.finish); return
            for i, (tipo, val) in enumerate(tasks):
                GLib.idle_add(self.progress.set_fraction, i / total)
                GLib.idle_add(self.progress.set_text, f"Tarea {i+1}/{total}: {val}")
                if tipo == "limpieza":
                    script = self.generate_bash_script_dynamic(val)
                    proc = subprocess.Popen(["pkexec", "bash", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout: self.log(line.strip())
                    proc.wait()
                    if os.path.exists(script): os.remove(script)
                else: self.run_clamav_logic(val)
            GLib.idle_add(self.finish)
        threading.Thread(target=worker, daemon=True).start()

    def generate_bash_script_dynamic(self, task):
        s = "#!/bin/bash\n"
        if task == "APT": s += "apt-get autoclean && apt-get autoremove -y\n"
        elif task == "Journal": s += "journalctl --vacuum-time=1d\n"
        elif task == "Temporales": s += "rm -rf /tmp/*\n"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sh", mode='w')
        tmp.write(s); tmp.close()
        os.chmod(tmp.name, stat.S_IRWXU)
        return tmp.name

    def finish(self):
        self.btn_run.set_sensitive(True)
        self.progress.set_fraction(1.0)
        self.progress.set_text("Completado")
        self.log("Mantenimiento finalizado.")
        subprocess.run(['notify-send', 'Tanuki!', 'Proceso completado'], stderr=subprocess.DEVNULL)

    def show_about(self, btn):
        about = Gtk.AboutDialog()
        about.set_program_name("Tanuki!")
        about.set_version("1.0")
        about.set_comments("Antivirus Frontend de ClamAV para CuerdOS.\nMantén tu sistema en perfecto estado.")
        about.set_copyright("🄯 2025 CuerdOS")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://cuerdos.github.io")
        about.set_website_label("Visitar sitio web")
        if os.path.exists(self.logo_path): about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(self.logo_path, 128, 128, True))
        about.set_transient_for(self); about.run(); about.destroy()

if __name__ == "__main__":
    app = AlecaishereApp(); app.connect("destroy", Gtk.main_quit); app.show_all(); Gtk.main()