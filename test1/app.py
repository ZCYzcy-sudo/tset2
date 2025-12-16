import sys
import warnings

# 忽略特定的PyQt5弃用警告
warnings.filterwarnings("ignore", message="sipPyTypeDict\(\) is deprecated, the extension module should use sipPyTypeDictRef\(\) instead")

import datetime
from getmac import get_mac_address
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QMessageBox, 
    QVBoxLayout, QHBoxLayout, QSpinBox, QGroupBox, QLayout
)
from PyQt5.QtCore import QTimer, QEvent, Qt
import psycopg2
from psycopg2 import OperationalError

# ---------------------- 数据库配置 ----------------------
DB_CONFIG = {
    "dbname": "auth_app",
    "user": "postgres",
    "password": "123456",  # 替换为你的PostgreSQL密码
    "host": "localhost",
    "port": "5432"
}

# ---------------------- 无操作提示窗口类 ----------------------
class InactivityWarningWindow(QWidget):
    def __init__(self, parent=None, timeout=5):
        super().__init__(parent)
        self.timeout = timeout
        self.remaining_time = timeout
        self.init_ui()
        self.start_countdown()
        
    def init_ui(self):
        self.setWindowTitle("无操作警告")
        self.setGeometry(800, 100, 300, 150)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        
        self.warning_label = QLabel(f"您已超过设定时间无操作，{self.remaining_time}秒后将强制登出！", self)
        self.warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.warning_label)
        
        self.close_btn = QPushButton("关闭警告", self)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)
        
        self.setLayout(layout)
    
    def start_countdown(self):
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)  # 每秒更新一次
        
    def update_countdown(self):
        self.remaining_time -= 1
        if self.remaining_time <= 0:
            self.countdown_timer.stop()
            self.parent().force_logout()
            self.close()
        else:
            self.warning_label.setText(f"您已超过设定时间无操作，{self.remaining_time}秒后将强制登出！")

# ---------------------- 核心功能类 ----------------------
class AuthApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("授权登录系统")
        self.setGeometry(400, 200, 350, 200)  # 窗口位置与大小
        self.user_activity_time = datetime.datetime.now()  # 记录最后操作时间
        self.logout_timer = None  # 强制登出定时器
        self.warning_timer = None  # 警告提示定时器
        self.inactivity_window = None  # 无操作提示窗口
        self.current_user = None  # 当前登录用户
        self.current_mac = None  # 当前设备MAC地址
        self.auth_end_date = None  # 授权截止日期
        self.inactivity_timeout = 30  # 默认30分钟无操作后提示
        self.warning_duration = 5  # 默认警告提示5秒后强制登出
        
        self.init_login_ui()  # 初始化登录界面
        self.init_db()  # 初始化数据库
        
        # 安装全局事件过滤器，监听用户操作
        self.installEventFilter(self)
    
    # 1. 初始化登录界面
    def init_login_ui(self):
        # 修复：先清除现有的布局
        if hasattr(self, 'layout'):
            current_layout = self.layout()
            if current_layout:
                QWidget().setLayout(current_layout)  # 这行代码会删除布局及其所有子组件
        
        self.setGeometry(400, 200, 350, 200)
        self.setWindowTitle("授权登录系统")
        
        layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("授权登录系统", self)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 用户名输入
        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("请输入用户名")
        layout.addWidget(self.username_input)
        
        # 密码输入
        self.password_input = QLineEdit(self)
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)
        
        # 登录按钮
        login_btn = QPushButton("登录", self)
        login_btn.clicked.connect(self.login)
        layout.addWidget(login_btn)
        
        self.setLayout(layout)
    
    # 2. 初始化主页界面
    def init_main_ui(self):
        # 修复：先清除现有的布局
        if hasattr(self, 'layout'):
            current_layout = self.layout()
            if current_layout:
                QWidget().setLayout(current_layout)  # 这行代码会删除布局及其所有子组件
        
        self.setGeometry(400, 200, 450, 350)
        self.setWindowTitle("授权登录系统 - 主页")
        
        main_layout = QVBoxLayout()
        
        # 用户信息区域
        user_info_group = QGroupBox("用户信息")
        user_info_layout = QVBoxLayout()
        
        self.welcome_label = QLabel(f"欢迎您，{self.current_user}！", self)
        self.welcome_label.setAlignment(Qt.AlignCenter)
        user_info_layout.addWidget(self.welcome_label)
        
        user_info_group.setLayout(user_info_layout)
        main_layout.addWidget(user_info_group)
        
        # 设备信息区域
        device_info_group = QGroupBox("设备信息")
        device_info_layout = QVBoxLayout()
        
        self.mac_label = QLabel(f"MAC地址：{self.current_mac}", self)
        device_info_layout.addWidget(self.mac_label)
        
        self.auth_date_label = QLabel(f"授权截止日期：{self.auth_end_date.strftime('%Y-%m-%d')}", self)
        device_info_layout.addWidget(self.auth_date_label)
        
        device_info_group.setLayout(device_info_layout)
        main_layout.addWidget(device_info_group)
        
        # 无操作设置区域
        inactivity_group = QGroupBox("无操作设置")
        inactivity_layout = QHBoxLayout()
        
        inactivity_layout.addWidget(QLabel("无操作提示时间（分钟）：", self))
        
        self.inactivity_spinbox = QSpinBox(self)
        self.inactivity_spinbox.setRange(1, 120)
        self.inactivity_spinbox.setValue(self.inactivity_timeout)
        self.inactivity_spinbox.valueChanged.connect(self.update_inactivity_timeout)
        inactivity_layout.addWidget(self.inactivity_spinbox)
        
        inactivity_group.setLayout(inactivity_layout)
        main_layout.addWidget(inactivity_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.logout_btn = QPushButton("登出", self)
        self.logout_btn.clicked.connect(self.logout)
        button_layout.addWidget(self.logout_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    # 3. 监听用户操作（鼠标、键盘）
    def eventFilter(self, obj, event):
        if event.type() in [QEvent.MouseButtonPress, QEvent.KeyPress]:
            self.user_activity_time = datetime.datetime.now()  # 更新最后操作时间
            # 如果警告窗口已打开，关闭它
            if self.inactivity_window and self.inactivity_window.isVisible():
                self.inactivity_window.close()
        return super().eventFilter(obj, event)
    
    # 4. 初始化数据库（创建表+插入默认数据）
    def init_db(self):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # 创建3张核心表（如果不存在）
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_info (
                    id SERIAL PRIMARY KEY,
                    mac_address VARCHAR(50) NOT NULL UNIQUE,
                    auth_end_date DATE NOT NULL,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    password VARCHAR(50) NOT NULL
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS login_logs (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL,
                    mac_address VARCHAR(50) NOT NULL,
                    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 插入默认用户数据（如果不存在）
            cur.execute("SELECT * FROM users WHERE username = 'admin'")
            if not cur.fetchone():
                cur.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin123')")
            
            # 插入默认授权数据（如果不存在）
            try:
                current_mac = get_mac_address()
                cur.execute("SELECT * FROM auth_info WHERE mac_address = %s", (current_mac,))
                if not cur.fetchone():
                    # 默认授权截止日期为当前时间 + 365天
                    default_end_date = datetime.datetime.now() + datetime.timedelta(days=365)
                    cur.execute(
                        "INSERT INTO auth_info (mac_address, auth_end_date) VALUES (%s, %s)",
                        (current_mac, default_end_date)
                    )
            except Exception as e:
                print(f"获取MAC地址失败：{str(e)}")

            conn.commit()
            cur.close()
            conn.close()
        except OperationalError as e:
            QMessageBox.critical(self, "数据库错误", f"数据库连接失败：{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"初始化数据库失败：{str(e)}")
    
    # 5. 登录验证
    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        try:
            current_mac = get_mac_address()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法获取设备MAC地址：{str(e)}")
            return

        current_time = datetime.datetime.now()

        # 步骤1：验证用户名密码不为空
        if not username or not password:
            QMessageBox.warning(self, "警告", "用户名或密码不能为空！")
            return

        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # 步骤2：验证用户名密码是否正确
            cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
            user = cur.fetchone()
            if not user:
                QMessageBox.warning(self, "失败", "用户名或密码错误！")
                cur.close()
                conn.close()
                return

            # 步骤3：验证MAC地址是否匹配
            cur.execute("SELECT * FROM auth_info WHERE mac_address = %s", (current_mac,))
            auth = cur.fetchone()
            if not auth:
                QMessageBox.warning(self, "失败", "当前设备未授权，禁止登录！")
                cur.close()
                conn.close()
                return

            # 步骤4：验证当前时间是否晚于授权截止日期
            auth_end_date = auth[2]  # auth_info表的auth_end_date字段
            if current_time.date() > auth_end_date:
                QMessageBox.warning(self, "失败", "授权已过期，禁止登录！")
                cur.close()
                conn.close()
                return

            # 步骤5：验证当前时间是否早于最后一次登录时间
            cur.execute("SELECT MAX(login_time) FROM login_logs WHERE username = %s", (username,))
            last_login_time = cur.fetchone()[0]
            if last_login_time and current_time < last_login_time:
                QMessageBox.warning(self, "失败", "系统时间异常（早于上次登录时间），禁止登录！")
                cur.close()
                conn.close()
                return

            # 步骤6：记录本次登录日志
            cur.execute("INSERT INTO login_logs (username, mac_address) VALUES (%s, %s)", (username, current_mac))
            conn.commit()
            
            # 登录成功：设置当前用户信息
            self.current_user = username
            self.current_mac = current_mac
            self.auth_end_date = auth_end_date
            
            QMessageBox.information(self, "成功", f"登录成功！欢迎您，{username}！")
            
            # 初始化并显示主页界面
            self.init_main_ui()
            
            # 启动无操作检测定时器
            self.start_logout_timer()
            
            cur.close()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"登录失败：{str(e)}")
    
    # 6. 启动无操作检测定时器
    def start_logout_timer(self):
        if self.logout_timer:
            self.logout_timer.stop()
        self.logout_timer = QTimer(self)
        self.logout_timer.timeout.connect(self.check_inactivity)
        self.logout_timer.start(1000)  # 每秒检查一次
    
    def check_inactivity(self):
        elapsed = (datetime.datetime.now() - self.user_activity_time).total_seconds() / 60
        if elapsed >= self.inactivity_timeout:
            # 显示无操作警告窗口
            self.show_inactivity_warning()
    
    def show_inactivity_warning(self):
        if not self.inactivity_window or not self.inactivity_window.isVisible():
            self.inactivity_window = InactivityWarningWindow(self, self.warning_duration)
            self.inactivity_window.show()
    
    def update_inactivity_timeout(self, value):
        self.inactivity_timeout = value
    
    # 7. 强制登出
    def force_logout(self):
        QMessageBox.warning(self, "提示", f"{self.inactivity_timeout}分钟无操作，已强制登出！")
        self.current_user = None
        self.current_mac = None
        self.auth_end_date = None
        self.user_activity_time = datetime.datetime.now()  # 重置活动时间
        self.init_login_ui()  # 返回登录界面
    
    # 8.MAC地址获取
    def get_current_mac(self):
        return get_mac_address()
    
    # 9. 登出功能
    def logout(self):
        """用户主动登出"""
        reply = QMessageBox.question(self, '确认登出', 
                                    '确定要登出系统吗？',
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # 清除用户信息
            self.current_user = None
            self.current_mac = None
            self.auth_end_date = None
            
            # 停止定时器
            if self.logout_timer:
                self.logout_timer.stop()
            
            # 关闭警告窗口
            if self.inactivity_window and self.inactivity_window.isVisible():
                self.inactivity_window.close()
            
            # 返回登录界面
            self.init_login_ui()
    
    # 10. 重写关闭事件
    def closeEvent(self, event):
        """重写关闭事件"""
        if self.current_user:  # 如果用户已登录
            reply = QMessageBox.question(self, '确认关闭', 
                                        '您当前已登录，关闭窗口将退出程序。是否确定关闭？',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# ---------------------- 打包为.exe入口 ----------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuthApp()
    window.show()
    sys.exit(app.exec_())