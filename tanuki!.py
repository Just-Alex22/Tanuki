#!/usr/bin/env python3

import gi
import os
import subprocess
import psutil
import tempfile
import stat
import threading
import shutil
from datetime import datetime

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
        self.log_file = os.path.expanduser("~/.tanuki_history.log")
        
        if not os.path.exists(self.quarantine_path):
            os.makedirs(self.quarantine_path)
        
        if os.path.exists(self.logo_path):
            self.set_icon_from_file(self.logo_path)

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        headerbar.set_title("Tanuki!")
        headerbar.set_subtitle("Powered by ClamAV")
        self.set_titlebar(headerbar)


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

        tab_general = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_all_compat(tab_general, 25)
        
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        status_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.DIALOG)
        status_label = Gtk.Label()
        status_label.set_markup("<span size='xx-large' weight='bold'>Sistema Protegido</span>")
        status_label.set_xalign(0)
        status_box.pack_start(status_icon, False, False, 0)
        status_box.pack_start(status_label, True, True, 0)
        tab_general.pack_start(status_box, False, False, 0)

        self.lbl_quarantine_info = Gtk.Label()
        self.lbl_quarantine_info.set_xalign(0)
        tab_general.pack_start(self.lbl_quarantine_info, False, False, 0)
        
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        tab_general.pack_start(sep, False, False, 5)

        profile_grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for label, p_type in [("Escaneo Rápido", "quick"), ("Escaneo General", "general"), ("Escaneo Completo", "full")]:
            btn = Gtk.Button(label=label)
            btn.set_size_request(-1, 80)
            btn.connect("clicked", self.apply_profile_and_run, p_type)
            profile_grid.pack_start(btn, True, True, 0)
        
        tab_general.pack_start(profile_grid, False, False, 0)
        self.notebook.append_page(tab_general, Gtk.Label(label="General"))

        tab_quarantine = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_all_compat(tab_quarantine, 12)
        
        self.q_store = Gtk.ListStore(str, str)
        self.q_tree = Gtk.TreeView(model=self.q_store)
        for i, title in enumerate(["Archivo detectado", "Ruta de origen"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            self.q_tree.append_column(column)
        
        q_scroll = Gtk.ScrolledWindow()
        q_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        q_scroll.add(self.q_tree)
        tab_quarantine.pack_start(q_scroll, True, True, 0)
        
        q_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_q_refresh = Gtk.Button(label="Refrescar")
        btn_q_refresh.connect("clicked", lambda x: self.refresh_quarantine())
        btn_q_del = Gtk.Button(label="Eliminar Definitivamente")
        btn_q_del.get_style_context().add_class("destructive-action")
        btn_q_del.connect("clicked", self.on_quarantine_delete)
        btn_q_rest = Gtk.Button(label="Restaurar Archivo")
        btn_q_rest.connect("clicked", self.on_quarantine_restore)
        
        for b in [btn_q_refresh, btn_q_rest, btn_q_del]: q_btns.pack_start(b, False, False, 0)
        tab_quarantine.pack_start(q_btns, False, False, 0)
        self.notebook.append_page(tab_quarantine, Gtk.Label(label="Cuarentena"))

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
        self.text_view = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text_view.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.05, 0.05, 0.05, 1))
        self.text_view.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 1, 0, 1))
        terminal_scroll = Gtk.ScrolledWindow(min_content_height=180); terminal_scroll.add(self.text_view)
        terminal_expander.add(terminal_scroll)
        right_content.pack_start(terminal_expander, False, False, 0)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_all_compat(bottom_box, 12)
        self.progress = Gtk.ProgressBar(show_text=True)
        bottom_box.pack_start(self.progress, False, False, 0)

        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_box.set_halign(Gtk.Align.END)
        
        btn_logs = Gtk.Button(label="Ver Historial")
        btn_logs.connect("clicked", self.show_history_dialog)

        btn_custom = Gtk.Button(label="Escanear Carpeta...")
        btn_custom.connect("clicked", self.on_custom_scan)

        self.btn_run = Gtk.Button(label="Iniciar Todo")
        self.btn_run.get_style_context().add_class("suggested-action")
        self.btn_run.connect("clicked", self.start_cleaning)
        
        for b in [btn_logs, btn_custom, self.btn_run]: 
            action_box.pack_start(b, False, False, 0)
            
        bottom_box.pack_start(action_box, False, False, 0)
        right_content.pack_start(bottom_box, False, False, 0)

        self.refresh_quarantine()
        self.update_system_info()
        GLib.timeout_add_seconds(2, self.update_system_info)

    def refresh_quarantine(self):
        self.q_store.clear()
        if not os.path.exists(self.quarantine_path): return
        files = os.listdir(self.quarantine_path)
        for f in files: self.q_store.append([f, f.replace(".infected", "")])
        self.lbl_quarantine_info.set_markup(f"<b>Cuarentena:</b> {len(files)} amenazas aisladas.")

    def on_quarantine_delete(self, btn):
        model, treeiter = self.q_tree.get_selection().get_selected()
        if treeiter:
            os.remove(os.path.join(self.quarantine_path, model[treeiter][0]))
            self.refresh_quarantine()

    def on_quarantine_restore(self, btn):
        model, treeiter = self.q_tree.get_selection().get_selected()
        if treeiter:
            filename = model[treeiter][0]
            dest = os.path.join(os.path.expanduser("~"), filename.replace(".infected", ""))
            try:
                shutil.move(os.path.join(self.quarantine_path, filename), dest)
                os.chmod(dest, 0o644)
                self.refresh_quarantine()
            except: pass

    def save_report(self, task_count, threats):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, "a") as f:
            f.write(f"[{now}] Tareas: {task_count} | Amenazas: {threats}\n")

    def show_history_dialog(self, btn):
        dialog = Gtk.MessageDialog(transient_for=self, title="Historial", message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK)
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f: content = "".join(f.readlines()[-15:])
            dialog.format_secondary_text(content if content else "Sin registros.")
        else: dialog.format_secondary_text("Aún no hay historial.")
        dialog.run(); dialog.destroy()

    def apply_profile_and_run(self, btn, p_type):
        all_h = ["scan_downloads", "scan_desktop", "scan_docs", "scan_pics", "scan_music", "scan_videos", "scan_templates", "scan_public"]
        all_s = ["scan_cache", "scan_config", "scan_local_bin", "scan_usr_local", "scan_cron", "scan_mnt", "scan_opt", "scan_ssh"]
        for s in all_h + all_s: getattr(self, s).set_active(False)
        if p_type == "quick": [getattr(self, x).set_active(True) for x in all_h[:2]]
        elif p_type == "general": [getattr(self, x).set_active(True) for x in all_h]
        elif p_type == "full": [getattr(self, x).set_active(True) for x in all_h + all_s]
        self.start_cleaning(None)

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
        tmp.write(s); tmp.close(); os.chmod(tmp.name, stat.S_IRWXU)
        return tmp.name

    def run_clamav_logic(self, path):
        if not pyclamd or not os.path.exists(path): return 0
        try:
            cd = pyclamd.ClamdUnixSocket()
            if cd.ping():
                self.log(f"Analizando: {path}")
                results = cd.multiscan_file(path)
                if results:
                    for f, r in results.items():
                        self.log(f"¡AMENAZA!: {r[1]} en {f}")
                        self.move_to_quarantine(f)
                    return len(results)
        except: return 0
        return 0

    def move_to_quarantine(self, file_path):
        try:
            name = os.path.basename(file_path)
            dest = os.path.join(self.quarantine_path, f"{name}.infected")
            shutil.move(file_path, dest); os.chmod(dest, 0o000)
            GLib.idle_add(self.refresh_quarantine)
        except: pass

    def set_margin_all_compat(self, widget, value):
        for m in ["top", "bottom", "start", "end"]: getattr(widget, f"set_margin_{m}")(value)

    def add_header_button(self, hb, icon, label, bin, pkg):
        i_path = os.path.join(self.base_path, icon)
        btn = Gtk.Button(); btn.set_relief(Gtk.ReliefStyle.NONE)
        if os.path.exists(i_path): btn.set_image(Gtk.Image.new_from_pixbuf(GdkPixbuf.Buf.new_from_file_at_scale(i_path, 24, 24, True) if hasattr(GdkPixbuf, 'Buf') else GdkPixbuf.Pixbuf.new_from_file_at_scale(i_path, 24, 24, True)))
        btn.connect("clicked", self.on_external_app_clicked, label, bin, pkg); hb.pack_start(btn)

    def on_external_app_clicked(self, btn, label, binary, package):
        if shutil.which(binary): subprocess.Popen([binary])

    def add_section(self, container, title, items):
        frame = Gtk.Frame(label=title); box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_all_compat(box, 10)
        for label, icon, active, attr_name in items:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hbox.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU), False, False, 0)
            chk = Gtk.CheckButton(label=label, active=active)
            hbox.pack_start(chk, True, True, 0); box.pack_start(hbox, False, False, 0)
            setattr(self, attr_name, chk)
        frame.add(box); container.pack_start(frame, False, False, 0)

    def log(self, text):
        buf = self.text_view.get_buffer()
        GLib.idle_add(lambda: buf.insert(buf.get_end_iter(), f"» {text}\n"))

    def update_system_info(self):
        try:
            d, m = psutil.disk_usage('/'), psutil.virtual_memory()
            self.disk_label.set_markup(f"<b>Disco:</b> {d.free//10**9}GB"); self.ram_label.set_markup(f"<b>RAM:</b> {m.percent}%"); self.cpu_label.set_markup(f"<b>CPU:</b> {psutil.cpu_percent()}%")
        except: pass
        return True

    def start_cleaning(self, btn):
        if self.btn_run.get_sensitive() == False: return
        self.btn_run.set_sensitive(False)
        tasks = []
        scan_map = {"scan_downloads": "~/Downloads", "scan_desktop": "~/Desktop", "scan_docs": "~/Documents", "scan_pics": "~/Pictures", "scan_music": "~/Music", "scan_videos": "~/Videos", "scan_templates": "~/Templates", "scan_public": "~/Public", "scan_cache": "~/.cache", "scan_config": "~/.config", "scan_local_bin": "~/.local/bin", "scan_usr_local": "/usr/local/bin", "scan_cron": "/var/spool/cron", "scan_mnt": "/mnt", "scan_opt": "/opt", "scan_ssh": "~/.ssh"}
        for t in ["chk_apt", "chk_journal", "chk_tmp", "chk_thumbs", "chk_trash", "chk_web_cache", "chk_orphans", "chk_app_logs"]:
            if getattr(self, t).get_active(): tasks.append(("limpieza", t.replace("chk_", "").upper()))
        for attr, path in scan_map.items():
            if getattr(self, attr).get_active(): tasks.append(("scan", os.path.expanduser(path)))

        def worker():
            threats_found = 0
            if not tasks: GLib.idle_add(self.finish); return
            for i, (tipo, val) in enumerate(tasks):
                GLib.idle_add(self.progress.set_fraction, (i+1)/len(tasks))
                if tipo == "limpieza":
                    script = self.generate_bash_script_dynamic(val)
                    subprocess.Popen(["pkexec", "bash", script]).wait()
                    if os.path.exists(script): os.remove(script)
                else: threats_found += self.run_clamav_logic(val)
            self.save_report(len(tasks), threats_found)
            GLib.idle_add(self.finish)
        threading.Thread(target=worker, daemon=True).start()

    def finish(self):
        self.btn_run.set_sensitive(True); self.progress.set_text("Completado"); self.log("--- FINALIZADO ---")

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
        about.set_version("1.1-2026")
        about.set_comments("Frontend de ClamAV para CuerdOS.\nMantén tu sistema en perfecto estado.")
        about.set_copyright("🄯 2026 CuerdOS")
        about.set_license_type(Gtk.License.LGPL_3_0)
        about.set_website("https://cuerdos.github.io")
        about.set_website_label("Visitar sitio web")
        if os.path.exists(self.logo_path): about.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(self.logo_path, 128, 128, True))
        about.set_transient_for(self); about.run(); about.destroy()

if __name__ == "__main__":
    app = AlecaishereApp(); app.connect("destroy", Gtk.main_quit); app.show_all(); Gtk.main()