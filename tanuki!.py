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
        self.set_default_size(1000, 850)
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
        self.set_margin_all_compat(sys_box, 8)
        sys_frame = Gtk.Frame(label="Monitor del Sistema")
        sys_frame.add(sys_box)
        self.disk_label, self.ram_label, self.cpu_label = Gtk.Label(xalign=0), Gtk.Label(xalign=0), Gtk.Label(xalign=0)
        for lbl in [self.disk_label, self.ram_label, self.cpu_label]: sys_box.pack_start(lbl, False, False, 0)
        sidebar.pack_start(sys_frame, False, False, 0)

        right_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        paned.pack2(right_content, True, True)

        self.notebook = Gtk.Notebook()
        self.set_margin_all_compat(self.notebook, 6)
        right_content.pack_start(self.notebook, True, True, 0)

        tab_maint_scroll = Gtk.ScrolledWindow()
        self.tab_maintenance = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_all_compat(self.tab_maintenance, 12)
        self.add_section(self.tab_maintenance, "Limpieza de Sistema", [
            ("Limpiar APT (Caché de paquetes)", "package-x-generic", True, "chk_apt"),
            ("Limpiar Logs Journal (Systemd)", "document-properties", True, "chk_journal"),
            ("Vaciar Temporales (/tmp)", "user-trash-full", True, "chk_tmp"),
            ("Limpiar Miniaturas (Thumbnails)", "image-x-generic", False, "chk_thumbs"),
            ("Vaciar Papelera de Reciclaje", "user-trash", False, "chk_trash"),
            ("Limpiar Caché de Navegación", "network-idle", False, "chk_web_cache"),
            ("Eliminar Paquetes Huérfanos", "edit-delete", False, "chk_orphans"),
            ("Limpiar Logs de Aplicaciones (~/.log)", "text-x-generic", False, "chk_app_logs"),
        ])
        tab_maint_scroll.add(self.tab_maintenance)
        self.notebook.append_page(tab_maint_scroll, Gtk.Label(label="Mantenimiento"))

        tab_home_scroll = Gtk.ScrolledWindow()
        self.tab_home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_all_compat(self.tab_home, 12)
        self.add_section(self.tab_home, "Seguridad de Usuario (Home)", [
            ("Analizar Descargas", "folder-download", True, "scan_downloads"),
            ("Analizar Escritorio", "user-desktop", True, "scan_desktop"),
            ("Analizar Documentos", "folder-documents", False, "scan_docs"),
            ("Analizar Imágenes", "folder-pictures", False, "scan_pics"),
            ("Analizar Música", "folder-music", False, "scan_music"),
            ("Analizar Videos", "folder-videos", False, "scan_videos"),
            ("Analizar Plantillas", "folder-templates", False, "scan_templates"),
            ("Analizar Carpeta Pública", "folder-publicshare", False, "scan_public"),
        ])
        tab_home_scroll.add(self.tab_home)
        self.notebook.append_page(tab_home_scroll, Gtk.Label(label="Seguridad Home"))

        tab_sys_scroll = Gtk.ScrolledWindow()
        self.tab_system = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_all_compat(self.tab_system, 12)
        self.add_section(self.tab_system, "Rutas de Malware Comunes", [
            ("Analizar Caché (.cache)", "folder-temp", True, "scan_cache"),
            ("Analizar Extensiones (.config)", "preferences-desktop-peripherals", True, "scan_config"),
            ("Analizar Binarios Locales (~/.local/bin)", "system-software-install", True, "scan_local_bin"),
            ("Analizar System Binaries (/usr/local/bin)", "system-run", False, "scan_usr_local"),
            ("Analizar Crontabs y Tareas", "appointment-new", False, "scan_cron"),
            ("Analizar Punto de Montaje (/mnt)", "drive-removable-media", False, "scan_mnt"),
            ("Analizar Carpeta de Opt (/opt)", "folder-remote", False, "scan_opt"),
            ("Analizar Directorio de SSH (.ssh)", "network-vpn", False, "scan_ssh"),
        ])
        tab_sys_scroll.add(self.tab_system)
        self.notebook.append_page(tab_sys_scroll, Gtk.Label(label="Rutas Críticas"))

        terminal_expander = Gtk.Expander(label="Consola de Actividad")
        terminal_expander.set_expanded(True)
        self.set_margin_all_compat(terminal_expander, 6)
        
        self.text_view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text_view.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.05, 0.05, 0.05, 1))
        self.text_view.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 1, 0, 1))
        self.text_view.override_font(Pango.FontDescription("Monospace 9"))
        
        terminal_scroll = Gtk.ScrolledWindow(min_content_height=180)
        terminal_scroll.add(self.text_view)
        terminal_expander.add(terminal_scroll)
        right_content.pack_start(terminal_expander, False, False, 0)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_all_compat(bottom_box, 12)
        self.progress = Gtk.ProgressBar(show_text=True)
        bottom_box.pack_start(self.progress, False, False, 0)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_box.set_halign(Gtk.Align.END)
        
        btn_update = Gtk.Button(label="Actualizar Firmas")
        btn_update.connect("clicked", self.update_signatures)
        
        btn_custom = Gtk.Button(label="Escanear Carpeta...")
        btn_custom.connect("clicked", self.on_custom_scan)

        self.btn_run = Gtk.Button(label="Iniciar Todo")
        self.btn_run.get_style_context().add_class("suggested-action")
        self.btn_run.connect("clicked", self.start_cleaning)

        for b in [btn_update, btn_custom, self.btn_run]: action_box.pack_start(b, False, False, 0)
        bottom_box.pack_start(action_box, False, False, 0)
        right_content.pack_start(bottom_box, False, False, 0)

        self.update_system_info()
        GLib.timeout_add_seconds(2, self.update_system_info)

    def generate_bash_script_dynamic(self, task):
        s = "#!/bin/bash\n"
        if task == "APT": s += "apt-get autoclean && apt-get autoremove -y\n"
        elif task == "JOURNAL": s += "journalctl --vacuum-time=1d\n"
        elif task == "TMP": s += "rm -rf /tmp/*\n"
        elif task == "THUMBS": s += "rm -rf ~/.cache/thumbnails/*\n"
        elif task == "TRASH": s += "rm -rf ~/.local/share/Trash/*\n"
        elif task == "ORPHANS": s += "pacman -Rns $(pacman -Qtdq) --noconfirm 2>/dev/null || apt-get autoremove -y\n"
        elif task == "WEB_CACHE": s += "rm -rf ~/.cache/google-chrome/* ~/.cache/mozilla/firefox/*\n"
        elif task == "APP_LOGS": s += "rm -rf ~/.log/* /var/log/*.log\n"
        
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sh", mode='w')
        tmp.write(s); tmp.close()
        os.chmod(tmp.name, stat.S_IRWXU)
        return tmp.name

    def run_clamav_logic(self, path):
        if not pyclamd or not os.path.exists(path):
            self.log(f"Saltando {path} (ClamAV no listo o ruta vacía)")
            return
        try:
            cd = pyclamd.ClamdUnixSocket()
            if cd.ping():
                self.log(f"Escaneando con ClamAV: {path}")
                results = cd.multiscan_file(path)
                if results:
                    for f, r in results.items():
                        self.log(f"¡AMENAZA!: {r[1]} en {f}")
                        self.move_to_quarantine(f)
                else: self.log(f"✓ {path} está limpio.")
        except Exception as e:
            self.log(f"Error en ClamAV: Asegúrate de que 'clamav-daemon' esté activo.")

    def move_to_quarantine(self, file_path):
        try:
            name = os.path.basename(file_path)
            dest = os.path.join(self.quarantine_path, f"{name}.infected")
            shutil.move(file_path, dest)
            os.chmod(dest, 0o000)
            self.log(f"☣ AISLADO: {name} movido a cuarentena.")
        except: pass


    def set_margin_all_compat(self, widget, value):
        for m in ["top", "bottom", "start", "end"]: getattr(widget, f"set_margin_{m}")(value)

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
            dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                                      buttons=Gtk.ButtonsType.YES_NO, text=f"{label} no está instalado")
            dialog.format_secondary_text(f"¿Deseas intentar instalar {label} ahora?")
            response = dialog.run(); dialog.destroy()
            if response == Gtk.ResponseType.YES:
                def install_worker():
                    self.log(f"--- INSTALANDO {label.upper()} ---")
                    cmd = f"apt update && apt install -y {package} || pacman -S --noconfirm {package}"
                    proc = subprocess.Popen(["pkexec", "bash", "-c", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in proc.stdout: self.log(line.strip())
                    proc.wait(); self.log(f"--- FINALIZADO ---")
                threading.Thread(target=install_worker, daemon=True).start()

    def add_section(self, container, title, items):
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_all_compat(box, 10)
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
        GLib.idle_add(lambda: adj.set_value(adj.get_upper()))

    def update_system_info(self):
        try:
            d, m = psutil.disk_usage('/'), psutil.virtual_memory()
            self.disk_label.set_markup(f"<b>Disco:</b> {d.free//10**9}GB libres")
            self.ram_label.set_markup(f"<b>RAM:</b> {m.percent}%")
            self.cpu_label.set_markup(f"<b>CPU:</b> {psutil.cpu_percent()}%")
        except: pass
        return True

    def update_signatures(self, btn):
        btn.set_sensitive(False)
        self.log("Actualizando firmas (freshclam)...")
        def worker():
            proc = subprocess.Popen(["pkexec", "freshclam"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout: self.log(line.strip())
            proc.wait()
            GLib.idle_add(btn.set_sensitive, True); self.log("Actualización finalizada.")
        threading.Thread(target=worker, daemon=True).start()

    def start_cleaning(self, btn):
        self.btn_run.set_sensitive(False)
        self.text_view.get_buffer().set_text("")
        tasks = []
        scan_map = {
            "scan_downloads": os.path.expanduser("~/Downloads"), "scan_desktop": os.path.expanduser("~/Desktop"),
            "scan_docs": os.path.expanduser("~/Documents"), "scan_pics": os.path.expanduser("~/Pictures"),
            "scan_music": os.path.expanduser("~/Music"), "scan_videos": os.path.expanduser("~/Videos"),
            "scan_templates": os.path.expanduser("~/Templates"), "scan_public": os.path.expanduser("~/Public"),
            "scan_cache": os.path.expanduser("~/.cache"), "scan_config": os.path.expanduser("~/.config"),
            "scan_local_bin": os.path.expanduser("~/.local/bin"), "scan_usr_local": "/usr/local/bin",
            "scan_cron": "/var/spool/cron", "scan_mnt": "/mnt", "scan_opt": "/opt", "scan_ssh": os.path.expanduser("~/.ssh")
        }
        for t in ["chk_apt", "chk_journal", "chk_tmp", "chk_thumbs", "chk_trash", "chk_web_cache", "chk_orphans", "chk_app_logs"]:
            if getattr(self, t).get_active(): tasks.append(("limpieza", t.replace("chk_", "").upper()))
        for attr, path in scan_map.items():
            if getattr(self, attr).get_active(): tasks.append(("scan", path))

        def worker():
            total = len(tasks)
            if total == 0: GLib.idle_add(self.finish); return
            for i, (tipo, val) in enumerate(tasks):
                GLib.idle_add(self.progress.set_fraction, (i+1)/total)
                GLib.idle_add(self.progress.set_text, f"Tarea {i+1}/{total}: {val}")
                if tipo == "limpieza":
                    script = self.generate_bash_script_dynamic(val)
                    proc = subprocess.Popen(["pkexec", "bash", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    if proc.stdout:
                        for line in proc.stdout: self.log(line.strip())
                    proc.wait()
                    if os.path.exists(script): os.remove(script)
                else:
                    self.run_clamav_logic(val)
            GLib.idle_add(self.finish)
        
        threading.Thread(target=worker, daemon=True).start()

    def finish(self):
        self.btn_run.set_sensitive(True)
        self.progress.set_text("Completado")
        self.log("--- PROCESO FINALIZADO CON ÉXITO ---")
        subprocess.run(['notify-send', 'Tanuki!', 'Mantenimiento y escaneo completados'], stderr=subprocess.DEVNULL)

    def on_custom_scan(self, btn):
        dlg = Gtk.FileChooserDialog(title="Seleccionar Carpeta", transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Analizar", Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            threading.Thread(target=self.run_clamav_logic, args=(path,), daemon=True).start()
        dlg.destroy()

    def show_about(self, btn):
        about = Gtk.AboutDialog()
        about.set_program_name("Tanuki!")
        about.set_version("1.0")
        about.set_comments("Frontend de ClamAV para CuerdOS.\nMantén tu sistema en perfecto estado.")
        about.set_copyright("🄯 2025 CuerdOS")
        about.set_license_type(Gtk.License.LGPL_3_0)
        about.set_website("https://cuerdos.github.io")
        about.set_website_label("Visitar sitio web")
        if os.path.exists(self.logo_path): about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(self.logo_path, 128, 128, True))
        about.set_transient_for(self); about.run(); about.destroy()

if __name__ == "__main__":
    app = AlecaishereApp(); app.connect("destroy", Gtk.main_quit); app.show_all(); Gtk.main()