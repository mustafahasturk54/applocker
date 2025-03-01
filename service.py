import sys
import os
import time
import psutil
import win32gui
import win32process
import win32con
import json
import win32api
import win32ui
import win32security
import ctypes
import winreg
from ctypes import wintypes
import win32com.client
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import cv2
import numpy as np
from cryptography.fernet import Fernet
from pathlib import Path
import math

# Windows API sabitleri
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

# Global değişkenler
keyboard_hook = None
mouse_hook = None
blocked_keys = [
    win32con.VK_LWIN, win32con.VK_RWIN,  # Windows tuşları
    win32con.VK_TAB,  # Tab tuşu
    win32con.VK_ESCAPE,  # ESC tuşu
    win32con.VK_CONTROL, win32con.VK_MENU,  # Ctrl ve Alt tuşları
    win32con.VK_DELETE,  # Delete tuşu
]

# Haar Cascade sınıflandırıcısını yükle
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

class KeyboardHook:
    def __init__(self):
        self.hooked = None
        
    def install(self):
        CMPFUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self.hooked = CMPFUNC(self.hook_procedure)
        self.hook = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self.hooked, None, 0
        )
        if not self.hook:
            return False
        return True
        
    def uninstall(self):
        if self.hooked is None:
            return
        ctypes.windll.user32.UnhookWindowsHookEx(self.hook)
        self.hooked = None
        
    def hook_procedure(self, code, wparam, lparam):
        if code == HC_ACTION and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            vk_code = ctypes.cast(lparam, ctypes.POINTER(ctypes.c_ulong))[0]
            if vk_code in blocked_keys:
                return 1
        return ctypes.windll.user32.CallNextHookEx(self.hook, code, wparam, lparam)

class AuthDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        self.setModal(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.is_verifying = False
        self.is_closing = False
        self.auth_method = "face" if settings.get('use_face_recognition', True) else "password"
        
        # Doğrula resmini yükle
        self.dogrula_img = cv2.imread('dogrula.png', cv2.IMREAD_UNCHANGED)
        if self.dogrula_img is None:
            print("Uyarı: dogrula.png yüklenemedi!")
            # Yedek olarak siyah bir resim oluştur
            self.dogrula_img = np.zeros((100, 100, 4), dtype=np.uint8)
        
        # Resmi BGRA formatına dönüştür (alfa kanalı için)
        if self.dogrula_img.shape[2] == 3:
            self.dogrula_img = cv2.cvtColor(self.dogrula_img, cv2.COLOR_BGR2BGRA)
        
        # Animasyon açısı
        self.loading_angle = 0
        
        # Overlay widget'ı oluştur ve tam ekran yap
        self.overlay = OverlayWidget()
        self.overlay.setWindowState(Qt.WindowState.WindowFullScreen)
        self.overlay.show()
        
        self.setup_ui()
        self.center_on_screen()
        
        # Timer süresini artır ve sadece pencere konumunu kontrol et
        self.stay_on_top_timer = QTimer(self)
        self.stay_on_top_timer.timeout.connect(self.check_focus)
        self.stay_on_top_timer.start(100)
        
        # Şifre alanına odaklan
        QTimer.singleShot(100, self.set_initial_focus)
        
        # Yüz tanıma için kamera
        self.cap = None
        if self.auth_method == "face":
            self.start_face_recognition()
    
    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
    
    def check_focus(self):
        self.center_on_screen()
        if not self.isActiveWindow():
            self.activateWindow()
            self.raise_()
            if self.auth_method == "password":
                self.password_input.setFocus()
    
    def set_initial_focus(self):
        self.activateWindow()
        self.raise_()
        if self.auth_method == "password":
            self.password_input.setFocus()
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Ana container widget
        container = QWidget()
        container.setObjectName("container")
        container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(container)
        
        # Üst bar
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(30)  # Yüksekliği 30 piksel yap
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(5, 2, 5, 2)  # Kenar boşluklarını azalt
        
        # Başlık
        title_label = QLabel("Kilit")  # Başlığı kısalt
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; color: white;")
        
        # Kapatma tuşu
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeButton")
        close_btn.clicked.connect(self.do_reject)
        close_btn.setFixedSize(16, 16)  # Buton boyutunu küçült
        
        top_layout.addWidget(title_label)
        top_layout.addWidget(close_btn)
        
        # Doğrulama metodu seçimi
        auth_method_layout = QHBoxLayout()
        
        face_btn = QPushButton("Yüz Tanıma")
        face_btn.setObjectName("faceButton")
        face_btn.setCheckable(True)
        face_btn.setChecked(self.auth_method == "face")
        face_btn.clicked.connect(lambda: self.switch_auth_method("face"))
        
        password_btn = QPushButton("Şifre")
        password_btn.setObjectName("passwordButton")
        password_btn.setCheckable(True)
        password_btn.setChecked(self.auth_method == "password")
        password_btn.clicked.connect(lambda: self.switch_auth_method("password"))
        
        auth_method_layout.addWidget(face_btn)
        auth_method_layout.addWidget(password_btn)
        
        # Yüz tanıma widget'ı
        self.face_widget = QWidget()
        face_layout = QVBoxLayout(self.face_widget)
        
        self.camera_label = QLabel()
        self.camera_label.setFixedSize(640, 480)  # Kamera boyutuyla aynı boyut
        self.camera_label.setStyleSheet("background-color: #1e1e1e; border-radius: 5px;")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # İçeriği ortala
        
        face_layout.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Şifre widget'ı
        self.password_widget = QWidget()
        password_layout = QVBoxLayout(self.password_widget)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Şifrenizi girin")
        self.password_input.returnPressed.connect(self.verify_password)
        
        verify_btn = QPushButton("Doğrula")
        verify_btn.clicked.connect(self.verify_password)
        verify_btn.setObjectName("verifyButton")
        
        # Şifremi unuttum butonu
        forgot_btn = QPushButton("Şifremi Unuttum")
        forgot_btn.setObjectName("forgotButton")
        forgot_btn.clicked.connect(self.forgot_password)
        
        password_layout.addWidget(QLabel("Şifrenizi girin:"))
        password_layout.addWidget(self.password_input)
        password_layout.addWidget(verify_btn)
        password_layout.addWidget(forgot_btn)
        
        # Widget'ları layout'a ekle
        layout.addWidget(top_bar)
        layout.addLayout(auth_method_layout)
        layout.addWidget(self.face_widget)
        layout.addWidget(self.password_widget)
        
        main_layout.addWidget(container)
        self.setLayout(main_layout)
        
        # Başlangıç durumunu ayarla
        self.face_widget.setVisible(self.auth_method == "face")
        self.password_widget.setVisible(self.auth_method == "password")
        
        # Stilleri ayarla
        self.setStyleSheet("""
            QWidget#container {
                background-color: #2b2b2b;
                border: 1px solid #3a3a3a;
                border-radius: 10px;
            }
            QWidget#topBar {
                background-color: #1e1e1e;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QPushButton {
                padding: 8px 15px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:checked {
                background-color: #1565C0;
            }
            QPushButton#closeButton {
                background-color: transparent;
                color: white;
                border: none;
                font-size: 16px;
                padding: 0;
            }
            QPushButton#closeButton:hover {
                background-color: #ff4444;
            }
            QPushButton#forgotButton {
                background-color: transparent;
                color: #2196F3;
                padding: 4px;
            }
            QPushButton#forgotButton:hover {
                color: #1976D2;
                text-decoration: underline;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
                background-color: #363636;
                color: white;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
            }
            QLabel {
                color: white;
            }
        """)
        
        self.setFixedSize(450, 400)  # Pencereyi büyüt
    
    def switch_auth_method(self, method):
        if method == self.auth_method:
            return
            
        self.auth_method = method
        self.face_widget.setVisible(method == "face")
        self.password_widget.setVisible(method == "password")
        
        if method == "face":
            self.setFixedSize(700, 600)
            self.start_face_recognition()
        else:
            self.setFixedSize(700, 300)
            self.stop_face_recognition()
            self.password_input.setFocus()
    
    def start_face_recognition(self):
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                QMessageBox.warning(self, "Hata", "Kamera başlatılamadı!")
                return
            
            # Kamera çözünürlüğünü ayarla
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            self.timer = QTimer()
            self.timer.timeout.connect(self.update_frame)
            self.timer.start(30)  # 30ms = ~30fps
            
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Kamera başlatılırken hata oluştu: {e}")
    
    def update_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return
        
        # Görüntüyü gri tonlamaya çevir
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Yüz tespiti yap
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        # Kamera boyutlarını al
        h, w = frame.shape[:2]
        
        # Kamera görüntüleme alanının boyutlarını al
        camera_w = self.camera_label.width()
        camera_h = self.camera_label.height()
        
        # Doğrula resminin boyutunu ayarla
        # Resmin en-boy oranını koru
        img_h, img_w = self.dogrula_img.shape[:2]
        aspect_ratio = img_w / img_h
        
        # Kamera görüntüleme alanına göre en uygun boyutu hesapla
        target_height = int(camera_h * 0.5)  # Kamera alanının %50'si
        target_width = int(target_height * aspect_ratio)
        
        # Eğer genişlik kamera genişliğini aşarsa, genişliğe göre ayarla
        if target_width > camera_w * 0.5:
            target_width = int(camera_w * 0.5)  # Kamera alanının %50'si
            target_height = int(target_width / aspect_ratio)
        
        # Resmi yeniden boyutlandır
        resized_dogrula = cv2.resize(self.dogrula_img, (target_width, target_height))
        
        # Resmi ortalamak için koordinatları hesapla
        x_offset = (camera_w - target_width) // 2
        y_offset = (camera_h - target_height) // 2
        
        # Siyah arka plan oluştur
        display_frame = np.zeros((camera_h, camera_w, 3), dtype=np.uint8)
        
        if len(faces) > 0:
            # İlk yüzü al ve işle
            (x, y, w_face, h_face) = faces[0]
            face_roi = gray[y:y+h_face, x:x+w_face]
            face_roi = cv2.resize(face_roi, (200, 200))
            
            if 'face_data' in self.settings:
                saved_faces = np.array(self.settings['face_data'])
                match_count = 0
                for saved_face in saved_faces:
                    mse = np.mean((face_roi - saved_face) ** 2)
                    if mse < 2000:
                        match_count += 1
                
                if match_count > len(saved_faces) * 0.5:
                    self.stop_face_recognition()
                    self.accept()
                    return
            
            # Yüz algılandığında normal resmi göster
            bgr = resized_dogrula[:, :, :3]
            alpha = resized_dogrula[:, :, 3]
            alpha_3d = np.stack([alpha/255.0]*3, axis=-1)
            
            # Resmi yerleştir
            roi = display_frame[y_offset:y_offset+target_height, x_offset:x_offset+target_width]
            display_frame[y_offset:y_offset+target_height, x_offset:x_offset+target_width] = \
                roi * (1 - alpha_3d) + bgr * alpha_3d
            
            text = "Yuz algilandi"
            color = (50, 50, 50)
        else:
            # Yüz algılanmadığında yarı saydam resmi göster
            bgr = resized_dogrula[:, :, :3]
            alpha = resized_dogrula[:, :, 3]
            alpha_3d = np.stack([alpha/255.0]*3, axis=-1)
            
            # Resmi yerleştir
            roi = display_frame[y_offset:y_offset+target_height, x_offset:x_offset+target_width]
            display_frame[y_offset:y_offset+target_height, x_offset:x_offset+target_width] = \
                roi * (1 - alpha_3d * 0.5) + bgr * (alpha_3d * 0.5)
            
            text = "Yuz bekleniyor..."
            color = (100, 100, 100)
        
        # Metni ekle
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        text_x = camera_w//2 - text_size[0] // 2
        text_y = y_offset + target_height + 30
        cv2.putText(display_frame, text, (text_x, text_y), font, 0.7, color, 2)
        
        # Frame'i göster
        h, w, ch = display_frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(display_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.camera_label.setPixmap(QPixmap.fromImage(qt_image))
    
    def stop_face_recognition(self):
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'cap'):
            self.cap.release()
        cv2.destroyAllWindows()
    
    def verify_password(self):
        if self.is_verifying or self.is_closing:
            return
            
        self.is_verifying = True
        
        try:
            if not self.settings['password']:
                QMessageBox.warning(self, "Hata", "Henüz şifre belirlenmemiş!")
                self.do_reject()
                return
                
            if self.password_input.text() == self.settings['password']:
                self.do_accept()
            else:
                QMessageBox.warning(self, "Hata", "Yanlış şifre!")
                self.password_input.clear()
                self.password_input.setFocus()
        finally:
            self.is_verifying = False
    
    def forgot_password(self):
        if self.is_verifying or self.is_closing:
            return
            
        recovery_password, ok = QInputDialog.getText(
            self,
            "Şifre Kurtarma",
            "Kurtarma şifresini girin:",
            QLineEdit.EchoMode.Password
        )
        
        if ok:
            if recovery_password == self.settings['recovery_password']:
                QMessageBox.information(
                    self,
                    "Başarılı",
                    f"Ana şifreniz: {self.settings['password']}"
                )
            else:
                QMessageBox.warning(self, "Hata", "Yanlış kurtarma şifresi!")
    
    def do_reject(self):
        if self.is_closing:
            return
            
        self.is_closing = True
        self.stop_face_recognition()
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.close()
            self.overlay = None
        super().reject()
        
    def do_accept(self):
        if self.is_closing:
            return
            
        self.is_closing = True
        self.stop_face_recognition()
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.close()
            self.overlay = None
        super().accept()
    
    def closeEvent(self, event):
        self.do_reject()
        event.accept()
    
    def reject(self):
        self.do_reject()
    
    def accept(self):
        self.do_accept()

class AppLockerService(QObject):
    def __init__(self):
        super().__init__()
        self.settings_path = os.path.join(os.getenv('APPDATA'), 'Kilit', 'settings.json')
        self.load_settings()
        
        # Sistem kısayolları için hook
        self.keyboard_hook = KeyboardHook()
        
        # İzin verilen uygulamalar listesi
        self.allowed_processes = set()
        
        # Aktif şifre pencereleri
        self.active_dialogs = {}
        
        # Kilitli uygulamaların pencerelerini takip et
        self.locked_windows = {}
        
        # Reddedilen uygulamalar listesi
        self.rejected_processes = set()
        
        # Son başarılı şifre girişi zamanı
        self.last_auth_time = {}
        self.auth_timeout = 300  # 5 dakika
        
        # Zamanlayıcılar oluştur
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_running_apps)
        self.check_timer.start(50)  # Her 50ms'de kontrol et
        
        self.verify_timer = QTimer()
        self.verify_timer.timeout.connect(self.verify_locked_apps)
        self.verify_timer.start(100)  # Her 100ms'de doğrula
        
        # Başlangıçta kısıtlamaları kaldır
        self.enable_task_manager()

    def disable_task_manager(self):
        try:
            # Görev yöneticisini registry üzerinden devre dışı bırak
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                 "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System")
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            
            # System Settings'i devre dışı bırak
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                 "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer")
            winreg.SetValueEx(key, "NoControlPanel", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Görev yöneticisi devre dışı bırakılamadı: {e}")

    def enable_task_manager(self):
        try:
            # Görev yöneticisini tekrar etkinleştir
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                 "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System")
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            
            # System Settings'i tekrar etkinleştir
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                 "Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer")
            winreg.SetValueEx(key, "NoControlPanel", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Görev yöneticisi etkinleştirilemedi: {e}")

    def check_running_apps(self):
        self.load_settings()
        has_locked_apps = False
        
        # Tüm çalışan uygulamaları kontrol et
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_name = proc.info['name']
                proc_path = proc.info['exe'] if proc.info['exe'] else ""
                pid = proc.info['pid']
                
                # Normal uygulama veya tam yol kontrolü (büyük-küçük harf duyarsız)
                is_locked = False
                for locked_app in self.settings['locked_apps']:
                    # Store uygulaması kontrolü
                    if "WindowsApps" in locked_app:
                        if proc_path and proc_path.lower().replace("\\", "/") == locked_app.lower().replace("\\", "/"):
                            is_locked = True
                            break
                    # Normal uygulama kontrolü
                    elif proc_name.lower() == locked_app.lower():
                        is_locked = True
                        break
                
                if is_locked:
                    has_locked_apps = True
                    
                    # Eğer bu process zaten doğrulanmışsa, atla
                    if pid in self.allowed_processes:
                        continue
                    
                    # Eğer bu process için zaten aktif bir şifre penceresi varsa, atla
                    if pid in self.active_dialogs:
                        dialog, _ = self.active_dialogs[pid]
                        if dialog.isVisible():
                            continue
                        else:
                            del self.active_dialogs[pid]
                    
                    # Process'in tüm pencerelerini bul ve kilitle
                    windows = self.get_all_windows(pid)
                    if not windows:  # Pencere yoksa atla
                        continue
                        
                    # Process'in ana penceresini bul
                    main_window = None
                    for hwnd in windows:
                        if win32gui.IsWindowVisible(hwnd) and not win32gui.GetParent(hwnd):
                            main_window = hwnd
                            break
                    
                    if main_window:
                        if main_window not in self.locked_windows:
                            # Pencereyi devre dışı bırak ve kilitle
                            self.disable_window(main_window)
                            self.locked_windows[main_window] = pid
                            
                            # Doğrulama dialog'unu göster
                            if pid not in self.active_dialogs:
                                dialog = AuthDialog(self.settings)
                                self.active_dialogs[pid] = (dialog, main_window)
                                
                                if dialog.exec() == QDialog.DialogCode.Accepted:
                                    self.allowed_processes.add(pid)
                                    # Tüm pencereleri etkinleştir
                                    for window in windows:
                                        self.enable_window(window)
                                        if window in self.locked_windows:
                                            del self.locked_windows[window]
                                else:
                                    try:
                                        # Process'i nazikçe kapatmayı dene
                                        proc.terminate()
                                        proc.wait(3)
                                    except psutil.TimeoutExpired:
                                        # Eğer nazikçe kapanmazsa zorla kapat
                                        proc.kill()
                                    except:
                                        pass
                                
                                if pid in self.active_dialogs:
                                    del self.active_dialogs[pid]
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Kilitli uygulama varsa kısıtlamaları etkinleştir, yoksa devre dışı bırak
        if has_locked_apps or self.active_dialogs:
            if not self.keyboard_hook.hooked:
                self.keyboard_hook.install()
                self.disable_task_manager()
        else:
            if self.keyboard_hook.hooked:
                self.keyboard_hook.uninstall()
                self.enable_task_manager()
        
        # Temizlik işlemleri
        self.cleanup_processes()

    def get_all_windows(self, pid):
        windows = []
        def callback(hwnd, _):
            try:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                    windows.append(hwnd)
            except:
                pass
        win32gui.EnumWindows(callback, None)
        return windows

    def cleanup_processes(self):
        # Kapalı process'leri temizle
        for pid in list(self.allowed_processes):
            try:
                proc = psutil.Process(pid)
                if not proc.is_running() or proc.name() not in self.settings['locked_apps']:
                    self.allowed_processes.remove(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.allowed_processes.remove(pid)
        
        # Kapalı process'leri reddedilenler listesinden temizle
        for pid in list(self.rejected_processes):
            try:
                proc = psutil.Process(pid)
                if not proc.is_running() or proc.name() not in self.settings['locked_apps']:
                    self.rejected_processes.remove(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.rejected_processes.remove(pid)
        
        # Kapalı pencereleri temizle
        for hwnd in list(self.locked_windows.keys()):
            try:
                if not win32gui.IsWindow(hwnd):
                    del self.locked_windows[hwnd]
            except:
                del self.locked_windows[hwnd]

    def __del__(self):
        # Servis kapatılırken kısıtlamaları kaldır
        if hasattr(self, 'keyboard_hook'):
            self.keyboard_hook.uninstall()
        self.enable_task_manager()

    def load_settings(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    'locked_apps': [],
                    'password': ''
                }
        except Exception as e:
            print(f"Ayarlar yüklenirken hata: {e}")
            self.settings = {
                'locked_apps': [],
                'password': ''
            }

    def disable_window(self, hwnd):
        # Pencereyi devre dışı bırak
        win32gui.EnableWindow(hwnd, False)
        # Pencereyi minimize et
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    def enable_window(self, hwnd):
        # Pencereyi tekrar etkinleştir
        win32gui.EnableWindow(hwnd, True)
        # Pencereyi geri yükle
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

    def get_window_handle(self, pid):
        result = []
        def callback(hwnd, _):
            try:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                    result.append(hwnd)
            except:
                pass
        win32gui.EnumWindows(callback, None)
        return result[0] if result else None

    def verify_locked_apps(self):
        # İzin verilen uygulamaları sürekli kontrol et
        for pid in list(self.allowed_processes):
            try:
                proc = psutil.Process(pid)
                if proc.name() in self.settings['locked_apps']:
                    # Eğer process yeniden başlatılmışsa
                    if proc.create_time() > time.time() - 1:  # Son 1 saniye içinde
                        self.allowed_processes.remove(pid)
                        try:
                            proc.suspend()  # Process'i dondur
                        except:
                            pass
            except:
                self.allowed_processes.remove(pid)

class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        # Tüm ekranları kapla
        self.cover_all_screens()
        
        # Yarı şeffaf siyah arka plan
        self.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        
        # Sistem kısayollarını engelle
        self.installEventFilter(self)
        
        # Alt kısmı da kapsayacak şekilde boyutu ayarla
        self.setWindowState(Qt.WindowState.WindowFullScreen)
    
    def cover_all_screens(self):
        # Tüm ekranları birleştiren geometriyi hesapla
        desktop = QApplication.primaryScreen()
        geometry = desktop.virtualGeometry()
        
        # Taskbar'ı da kapsayacak şekilde boyutu ayarla
        self.setGeometry(geometry)
        self.setFixedSize(geometry.width(), geometry.height())
        
        # Alt kısmı da kaplamak için
        self.setWindowState(Qt.WindowState.WindowFullScreen)
    
    def showEvent(self, event):
        super().showEvent(event)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.activateWindow()
        self.raise_()

class FaceRecognitionService:
    def __init__(self):
        self.face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
        self.animation_frame = 0
        self.last_animation_time = 0
        self.animation_interval = 100  # ms
        self.verified = False
        self.loading_angle = 0
        
    def draw_loading_animation(self, frame):
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2
        
        # Siyah arka plan
        frame.fill(0)
        
        # Yükleme animasyonu (dönen daire)
        radius = min(w, h) // 6
        start_angle = self.loading_angle
        end_angle = start_angle + 270
        
        # Beyaz daire (arka plan)
        cv2.circle(frame, (center_x, center_y), radius, (255, 255, 255), 2)
        
        # Mavi daire (yükleniyor)
        for angle in range(int(start_angle), int(end_angle), 5):
            rad = math.radians(angle)
            x = int(center_x + radius * math.cos(rad))
            y = int(center_y + radius * math.sin(rad))
            cv2.circle(frame, (x, y), 2, (255, 200, 0), -1)
        
        # Metin
        font = cv2.FONT_HERSHEY_SIMPLEX
        if self.verified:
            text = "Yuz dogrulandi"
            color = (0, 255, 0)
        else:
            text = "Yuz dogrulaniyor..."
            color = (200, 200, 200)
            
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        text_x = center_x - text_size[0] // 2
        text_y = center_y + radius + 40
        cv2.putText(frame, text, (text_x, text_y), font, 0.7, color, 2)
        
        return frame
    
    def update_animation(self):
        current_time = cv2.getTickCount() / cv2.getTickFrequency() * 1000
        
        if current_time - self.last_animation_time > self.animation_interval:
            self.loading_angle = (self.loading_angle + 10) % 360
            self.last_animation_time = current_time
    
    def update_frame(self, frame):
        # Siyah ekran oluştur
        display_frame = np.zeros_like(frame)
        
        # Yüz tanıma işlemi arka planda devam eder
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) > 0:
            self.verified = True
        else:
            self.verified = False
        
        # Animasyonu güncelle ve çiz
        self.update_animation()
        display_frame = self.draw_loading_animation(display_frame)
        
        return display_frame

if __name__ == '__main__':
    app = QApplication(sys.argv)
    service = AppLockerService()
    sys.exit(app.exec()) 