import sys
import os
import psutil
import win32gui
import win32process
import win32con
import win32api
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from cryptography.fernet import Fernet
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
from service import AppLockerService
import win32com.client

# Haar Cascade sınıflandırıcısını yükle
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

class PasswordDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Ayarlar - Şifre")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Şifre alanı
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Şifrenizi girin")
        
        # Butonlar
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.verify_password)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(QLabel("Ayarlara erişmek için şifrenizi girin:"))
        layout.addWidget(self.password_input)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
        # Stil
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QLabel {
                color: white;
            }
            QLineEdit {
                padding: 8px;
                background-color: #1e1e1e;
                color: white;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
    
    def verify_password(self):
        if self.password_input.text() == self.settings.get('password', ''):
            self.accept()
        else:
            QMessageBox.warning(self, "Hata", "Yanlış şifre!")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_path = os.path.join(os.getenv('APPDATA'), 'Kilit', 'settings.json')
        self.load_settings()
        self.setup_ui()
        self.setup_tray()
        
        # Servis başlat
        self.service = AppLockerService()
        
        # Başlangıçta gizle
        self.hide()

    def setup_ui(self):
        self.setWindowTitle("Kilit")
        self.setMinimumSize(800, 600)
        
        # Ana widget ve layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Ayarlar ve uygulama listesi için tab widget
        tab_widget = QTabWidget()
        
        # Kilitli uygulamalar sekmesi
        apps_tab = QWidget()
        apps_layout = QVBoxLayout(apps_tab)
        
        # Uygulama listesi
        self.apps_list = QListWidget()
        self.apps_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.update_apps_list()
        
        # Butonlar için layout
        buttons_layout = QHBoxLayout()
        
        # Uygulama ekle butonu
        add_app_btn = QPushButton("Uygulama Ekle")
        add_app_btn.clicked.connect(self.add_app)
        
        # Uygulama kaldır butonu
        remove_app_btn = QPushButton("Seçili Uygulamayı Kaldır")
        remove_app_btn.clicked.connect(self.remove_app)
        
        buttons_layout.addWidget(add_app_btn)
        buttons_layout.addWidget(remove_app_btn)
        
        apps_layout.addWidget(self.apps_list)
        apps_layout.addLayout(buttons_layout)
        
        # Ayarlar sekmesi
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        
        # Şifre ayarları için grup kutusu
        password_group = QGroupBox("Şifre Ayarları")
        password_layout = QVBoxLayout(password_group)
        
        # Ana şifre
        main_password_layout = QHBoxLayout()
        main_password_label = QLabel("Ana Şifre:")
        self.main_password_input = QLineEdit()
        self.main_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        main_password_layout.addWidget(main_password_label)
        main_password_layout.addWidget(self.main_password_input)
        
        # Kurtarma şifresi
        recovery_password_layout = QHBoxLayout()
        recovery_password_label = QLabel("Kurtarma Şifresi:")
        self.recovery_password_input = QLineEdit()
        self.recovery_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        recovery_password_layout.addWidget(recovery_password_label)
        recovery_password_layout.addWidget(self.recovery_password_input)
        
        # Şifreleri göster/gizle
        self.show_passwords_cb = QCheckBox("Şifreleri Göster")
        self.show_passwords_cb.stateChanged.connect(self.toggle_password_visibility)
        
        password_layout.addLayout(main_password_layout)
        password_layout.addLayout(recovery_password_layout)
        password_layout.addWidget(self.show_passwords_cb)
        
        # Yüz tanıma ayarları için grup kutusu
        face_group = QGroupBox("Yüz Tanıma Ayarları")
        face_layout = QVBoxLayout(face_group)
        
        # Yüz tanıma kullan
        self.use_face_recognition = QCheckBox("Yüz tanıma kullan")
        self.use_face_recognition.setChecked(self.settings.get('use_face_recognition', True))
        
        # Yüz verisi ekle/sil butonları
        face_buttons_layout = QHBoxLayout()
        
        add_face_btn = QPushButton("Yüz Tanıma Verisi Ekle")
        add_face_btn.clicked.connect(self.add_face_data)
        
        remove_face_btn = QPushButton("Yüz Tanıma Verisini Sil")
        remove_face_btn.clicked.connect(self.remove_face_data)
        
        face_buttons_layout.addWidget(add_face_btn)
        face_buttons_layout.addWidget(remove_face_btn)
        
        face_layout.addWidget(self.use_face_recognition)
        face_layout.addLayout(face_buttons_layout)
        
        # Genel ayarlar için grup kutusu
        general_group = QGroupBox("Genel Ayarlar")
        general_layout = QVBoxLayout(general_group)
        
        # Windows başlangıcında çalıştır
        self.startup_cb = QCheckBox("Windows başlangıcında çalıştır")
        self.startup_cb.setChecked(self.settings.get('run_at_startup', True))
        
        general_layout.addWidget(self.startup_cb)
        
        # Ayarları kaydet butonu
        save_btn = QPushButton("Ayarları Kaydet")
        save_btn.clicked.connect(self.save_settings)
        
        settings_layout.addWidget(password_group)
        settings_layout.addWidget(face_group)
        settings_layout.addWidget(general_group)
        settings_layout.addWidget(save_btn)
        settings_layout.addStretch()
        
        # Sekmeleri ekle
        tab_widget.addTab(apps_tab, "Kilitli Uygulamalar")
        tab_widget.addTab(settings_tab, "Ayarlar")
        
        layout.addWidget(tab_widget)
        
        # Mevcut şifreleri göster
        self.main_password_input.setText(self.settings.get('password', ''))
        self.recovery_password_input.setText(self.settings.get('recovery_password', ''))
        
        # Stil ayarları
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QTabWidget {
                background-color: #2b2b2b;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #1e1e1e;
                color: white;
                padding: 8px 15px;
                border: 1px solid #3a3a3a;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #2b2b2b;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: white;
                border: 1px solid #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #2196F3;
            }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
            QLineEdit {
                padding: 8px;
                background-color: #1e1e1e;
                color: white;
                border: 1px solid #3a3a3a;
                border-radius: 5px;
            }
            QLineEdit:focus {
                border: 1px solid #2196F3;
            }
            QLabel {
                color: white;
            }
            QCheckBox {
                color: white;
            }
            QGroupBox {
                color: white;
                border: 1px solid #3a3a3a;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
        """)

    def setup_tray(self):
        # Sistem tray ikonunu oluştur
        self.tray_icon = QSystemTrayIcon(self)
        icon = QIcon("app.ico")
        self.tray_icon.setIcon(icon)
        self.setWindowIcon(icon)
        
        # Tray menüsünü oluştur
        tray_menu = QMenu()
        
        # Göster/Gizle aksiyonu
        show_action = QAction("Ayarlar", self)
        show_action.triggered.connect(self.show_settings)
        tray_menu.addAction(show_action)
        
        # Ayırıcı
        tray_menu.addSeparator()
        
        # Çıkış aksiyonu
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)
        
        # Menüyü tray ikonuna bağla
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
    
    def show_settings(self):
        # Şifre doğrulama
        dialog = PasswordDialog(self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.show()
            self.activateWindow()
    
    def closeEvent(self, event):
        # Çarpıya basıldığında uygulamayı kapatmak yerine sistem tray'e küçült
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Kilit",
            "Uygulama arka planda çalışmaya devam ediyor.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def add_app(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Uygulama Seç",
            "",
            "Uygulamalar (*.exe)"
        )
        
        if file_path:
            app_name = os.path.basename(file_path)
            if app_name not in self.settings['locked_apps']:
                self.settings['locked_apps'].append(app_name)
                self.save_settings()
                self.update_apps_list()

    def remove_app(self):
        current_item = self.apps_list.currentItem()
        if current_item:
            app_name = current_item.text()
            self.settings['locked_apps'].remove(app_name)
            self.save_settings()
            self.update_apps_list()

    def update_apps_list(self):
        self.apps_list.clear()
        for app in self.settings['locked_apps']:
            self.apps_list.addItem(app)

    def toggle_password_visibility(self, state):
        echo_mode = (QLineEdit.EchoMode.Normal if state 
                    else QLineEdit.EchoMode.Password)
        self.main_password_input.setEchoMode(echo_mode)
        self.recovery_password_input.setEchoMode(echo_mode)

    def add_face_data(self):
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                QMessageBox.warning(self, "Hata", "Kamera başlatılamadı!")
                return
            
            face_samples = []
            sample_count = 0
            required_samples = 30
            
            while sample_count < required_samples:
                ret, frame = cap.read()
                if not ret:
                    break
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.3, 5)
                
                if len(faces) == 1:  # Sadece bir yüz tespit edildiğinde
                    (x, y, w, h) = faces[0]
                    face_roi = gray[y:y+h, x:x+w]
                    face_roi = cv2.resize(face_roi, (200, 200))
                    face_samples.append(face_roi.tolist())
                    sample_count += 1
                    
                    # İlerlemeyi göster
                    progress = int((sample_count / required_samples) * 100)
                    QApplication.processEvents()
                
                # ESC tuşu ile iptal
                if cv2.waitKey(1) == 27:
                    break
            
            cap.release()
            cv2.destroyAllWindows()
            
            if sample_count == required_samples:
                self.settings['face_data'] = face_samples
                self.save_settings()
                QMessageBox.information(self, "Başarılı", "Yüz tanıma verisi kaydedildi!")
            else:
                QMessageBox.warning(self, "Hata", "Yüz tanıma verisi kaydedilemedi!")
                
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Yüz tanıma verisi eklenirken hata oluştu: {e}")

    def remove_face_data(self):
        if 'face_data' in self.settings:
            del self.settings['face_data']
            self.save_settings()
            QMessageBox.information(self, "Başarılı", "Yüz tanıma verisi silindi!")
        else:
            QMessageBox.warning(self, "Hata", "Kayıtlı yüz tanıma verisi bulunamadı!")

    def save_settings(self):
        # Şifreleri kontrol et
        main_password = self.main_password_input.text()
        recovery_password = self.recovery_password_input.text()
        
        if not main_password or not recovery_password:
            QMessageBox.warning(self, "Hata", "Ana şifre ve kurtarma şifresi boş bırakılamaz!")
            return
        
        # Ayarları güncelle
        self.settings['password'] = main_password
        self.settings['recovery_password'] = recovery_password
        self.settings['use_face_recognition'] = self.use_face_recognition.isChecked()
        self.settings['run_at_startup'] = self.startup_cb.isChecked()
        
        # Başlangıçta çalıştırma ayarını güncelle
        startup_path = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft\\Windows\\Start Menu\\Programs\\Startup',
            'Kilit.lnk'
        )
        
        if self.settings['run_at_startup']:
            # Başlangıç kısayolu oluştur
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(startup_path)
            shortcut.Targetpath = sys.executable
            shortcut.Arguments = os.path.abspath(__file__)
            shortcut.WorkingDirectory = os.path.dirname(os.path.abspath(__file__))
            shortcut.save()
        else:
            # Başlangıç kısayolunu kaldır
            if os.path.exists(startup_path):
                os.remove(startup_path)
        
        # Ayarları kaydet
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        with open(self.settings_path, 'w') as f:
            json.dump(self.settings, f)
        
        QMessageBox.information(self, "Başarılı", "Ayarlar kaydedildi!")

    def load_settings(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {
                    'locked_apps': [],
                    'password': '',
                    'recovery_password': '',
                    'use_face_recognition': True,
                    'run_at_startup': True
                }
        except Exception as e:
            print(f"Ayarlar yüklenirken hata: {e}")
            self.settings = {
                'locked_apps': [],
                'password': '',
                'recovery_password': '',
                'use_face_recognition': True,
                'run_at_startup': True
            }

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec()) 