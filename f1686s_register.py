# -*- coding: utf-8 -*-
"""
F1686S Auto Register Tool
Antidetect Browser with Fake Fingerprint
Multi-threaded support
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import json
import os
import random
import string
import time
import requests
import base64
import tempfile
from datetime import datetime
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

# Selenium và các thư viện antidetect
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    from selenium_stealth import stealth
except ImportError:
    print("Cần cài đặt: pip install selenium selenium-stealth webdriver-manager")

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("Cần cài đặt: pip install webdriver-manager")

try:
    from fake_useragent import UserAgent
except ImportError:
    print("Cần cài đặt: pip install fake-useragent")

CONFIG_FILE = "config.json"

# Thread-safe lock cho các operations
bank_lock = threading.Lock()
log_lock = threading.Lock()
result_lock = threading.Lock()
counter_lock = threading.Lock()

class FProxyAPI:
    """API xoay proxy từ fproxy.me"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://fproxy.me/api/getnew"
    
    def get_new_proxy(self, location=None, ip_allow=None):
        """Lấy proxy mới"""
        params = {"api_key": self.api_key}
        if location is not None:
            params["location"] = location
        if ip_allow:
            params["ip_allow"] = ip_allow
            
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            data = response.json()
            # Dù success=false vẫn có thể có data proxy
            if data.get("data"):
                proxy_data = data["data"]
                return {
                    "success": True,
                    "proxy": proxy_data.get("httpuserpass"),
                    "http": proxy_data.get("http"),
                    "user": proxy_data.get("user"),
                    "pass": proxy_data.get("pass"),
                    "ip": proxy_data.get("ip"),
                    "port": proxy_data.get("port"),
                    "location": proxy_data.get("location"),
                    "message": data.get("message", "OK")
                }
            return {"success": False, "message": data.get("message", "Không lấy được proxy")}
        except Exception as e:
            return {"success": False, "message": str(e)}


class AnticaptchaAPI:
    """API giải captcha từ anticaptcha.top"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://anticaptcha.top/api/captcha"
    
    def solve_image_captcha(self, img, captcha_type=56, listcolor=""):
        """Giải captcha ảnh"""
        payload = {
            "apikey": self.api_key,
            "img": img,
            "type": captcha_type,
            "listcolor": listcolor
        }
        
        try:
            response = requests.post(self.base_url, json=payload, timeout=60)
            data = response.json()
            if data.get("success"):
                return {"success": True, "captcha": data.get("captcha")}
            return {"success": False, "message": data.get("message", "Giải captcha thất bại")}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def solve_geetest_captcha(self, image_base64_or_url, click_type="geetest2"):
        """
        Giải Geetest Image Captcha
        click_type: 
            - "geetest" = trả về tọa độ (x=56,y=99;...)
            - "geetest2" = trả về thứ tự ảnh (1,8,9)
        """
        # Step 1: Gửi captcha
        payload = {
            "key": self.api_key,
            "method": "base64",
            "textinstructions": "geetesticonv4",
            "click": click_type,
            "body": image_base64_or_url,
            "json": 1
        }
        
        try:
            response = requests.post("https://anticaptcha.top/in.php", json=payload, timeout=60)
            data = response.json()
            
            if data.get("status") != 1:
                return {"success": False, "message": data.get("request", "Gửi captcha thất bại")}
            
            task_id = data.get("request")
            print(f"Geetest task ID: {task_id}")
            
            # Step 2: Chờ kết quả
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(3)
                
                result_url = f"https://anticaptcha.top/res.php?key={self.api_key}&id={task_id}&json=1"
                result_response = requests.get(result_url, timeout=30)
                result_data = result_response.json()
                
                if result_data.get("status") == 1:
                    captcha_result = result_data.get("request", "")
                    print(f"Geetest result: {captcha_result}")
                    return {"success": True, "result": captcha_result}
                elif result_data.get("request") == "CAPCHA_NOT_READY":
                    print(f"Đang chờ giải captcha... ({attempt + 1}/{max_attempts})")
                    continue
                else:
                    return {"success": False, "message": result_data.get("request", "Lỗi không xác định")}
            
            return {"success": False, "message": "Timeout chờ kết quả captcha"}
            
        except Exception as e:
            return {"success": False, "message": str(e)}


class ViOTPAPI:
    """API thuê số điện thoại từ viotp.com"""
    
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.viotp.com"
    
    def get_balance(self):
        """Kiểm tra số dư"""
        try:
            url = f"{self.base_url}/users/balance?token={self.token}"
            response = requests.get(url, timeout=30)
            data = response.json()
            if data.get("success"):
                return {"success": True, "balance": data["data"]["balance"]}
            return {"success": False, "message": data.get("message")}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def request_phone(self, service_id, network=None):
        """Thuê số điện thoại"""
        try:
            url = f"{self.base_url}/request/getv2?token={self.token}&serviceId={service_id}"
            if network:
                url += f"&network={network}"
            
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if data.get("success"):
                phone_data = data["data"]
                return {
                    "success": True,
                    "phone": phone_data.get("phone_number"),
                    "request_id": phone_data.get("request_id"),
                    "balance": phone_data.get("balance")
                }
            return {"success": False, "message": data.get("message"), "status_code": data.get("status_code")}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_otp(self, request_id, max_wait=120):
        """Lấy OTP từ số đã thuê"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                url = f"{self.base_url}/session/getv2?requestId={request_id}&token={self.token}"
                response = requests.get(url, timeout=30)
                data = response.json()
                
                if data.get("success") and data.get("data"):
                    otp_data = data["data"]
                    status = otp_data.get("Status")
                    
                    if status == 1:  # Hoàn thành
                        return {
                            "success": True,
                            "code": otp_data.get("Code"),
                            "sms_content": otp_data.get("SmsContent")
                        }
                    elif status == 2:  # Hết hạn
                        return {"success": False, "message": "OTP đã hết hạn"}
                
                time.sleep(5)
            except Exception as e:
                time.sleep(5)
        
        return {"success": False, "message": "Timeout chờ OTP"}


class WindowManager:
    """Quản lý sắp xếp cửa sổ browser"""
    
    # Kích thước mobile
    MOBILE_WIDTH = 400
    MOBILE_HEIGHT = 750
    
    # Vị trí đã sử dụng
    used_positions = []
    position_lock = threading.Lock()
    
    @classmethod
    def get_next_position(cls, thread_id):
        """Lấy vị trí tiếp theo cho cửa sổ browser"""
        with cls.position_lock:
            # Tính toán vị trí dựa trên thread_id
            # Sắp xếp theo hàng, mỗi hàng 4 cửa sổ
            cols_per_row = 4
            padding = 10
            
            col = thread_id % cols_per_row
            row = thread_id // cols_per_row
            
            x = col * (cls.MOBILE_WIDTH + padding) + padding
            y = row * (cls.MOBILE_HEIGHT + padding) + padding
            
            return x, y
    
    @classmethod
    def reset_positions(cls):
        """Reset danh sách vị trí"""
        with cls.position_lock:
            cls.used_positions.clear()


class AntidetectBrowser:
    """Browser antidetect với fake fingerprint - Mobile mode"""
    
    def __init__(self, proxy=None, proxy_user=None, proxy_pass=None, thread_id=0):
        self.driver = None
        self.proxy = proxy
        self.proxy_user = proxy_user
        self.proxy_pass = proxy_pass
        self.thread_id = thread_id
    
    def create_browser(self):
        """Tạo browser với antidetect settings - Mobile size"""
        options = Options()
        
        # Mobile screen size
        width = WindowManager.MOBILE_WIDTH
        height = WindowManager.MOBILE_HEIGHT
        
        # Antidetect arguments
        options.add_argument(f"--window-size={width},{height}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-notifications")
        
        # Mobile emulation
        mobile_emulation = {
            "deviceMetrics": {"width": width, "height": height, "pixelRatio": 2.0},
            "userAgent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        }
        options.add_experimental_option("mobileEmulation", mobile_emulation)
        
        # Proxy settings
        if self.proxy:
            if self.proxy_user and self.proxy_pass:
                # Proxy với authentication
                proxy_str = f"{self.proxy}"
                options.add_argument(f"--proxy-server=http://{proxy_str}")
            else:
                options.add_argument(f"--proxy-server=http://{self.proxy}")
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Random language
        languages = ["en-US,en", "vi-VN,vi", "en-GB,en"]
        options.add_argument(f"--lang={random.choice(languages)}")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except:
            self.driver = webdriver.Chrome(options=options)
        
        # Set window position
        x, y = WindowManager.get_next_position(self.thread_id)
        self.driver.set_window_position(x, y)
        self.driver.set_window_size(WindowManager.MOBILE_WIDTH, WindowManager.MOBILE_HEIGHT)
        
        # Apply stealth mode
        stealth(self.driver,
            languages=["vi-VN", "vi", "en-US", "en"],
            vendor="Google Inc.",
            platform="Linux armv81",
            webgl_vendor="Qualcomm",
            renderer="Adreno (TM) 650",
            fix_hairline=True,
        )
        
        # Override navigator properties for mobile
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['vi-VN', 'vi', 'en-US', 'en']
                });
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Linux armv81'
                });
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 5
                });
                window.chrome = {
                    runtime: {}
                };
            """
        })
        
        return self.driver
    
    def human_type(self, element, text, min_delay=0.05, max_delay=0.15):
        """Gõ phím như người thật"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))
    
    def human_click(self, element):
        """Click như người thật"""
        actions = ActionChains(self.driver)
        actions.move_to_element(element)
        time.sleep(random.uniform(0.1, 0.3))
        actions.click()
        actions.perform()
    
    def random_mouse_move(self):
        """Di chuột ngẫu nhiên"""
        try:
            actions = ActionChains(self.driver)
            for _ in range(random.randint(2, 5)):
                x_offset = random.randint(-50, 50)
                y_offset = random.randint(-50, 50)
                actions.move_by_offset(x_offset, y_offset)
                time.sleep(random.uniform(0.1, 0.3))
            actions.perform()
        except:
            pass
    
    def wait_and_find(self, by, value, timeout=15):
        """Chờ và tìm element"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except:
            return None
    
    def fill_registration_form(self, username, password, phone, fullname):
        """Điền form đăng ký"""
        try:
            time.sleep(random.uniform(1, 2))
            
            # === 1. Điền Username ===
            account_input = self.wait_and_find(By.CSS_SELECTOR, 'input[data-input-name="account"]')
            if account_input:
                self.human_click(account_input)
                time.sleep(random.uniform(0.3, 0.6))
                account_input.clear()
                self.human_type(account_input, username)
                time.sleep(random.uniform(0.5, 1))
            
            # === 2. Điền Password ===
            password_input = self.wait_and_find(By.CSS_SELECTOR, 'input[data-input-name="userpass"]')
            if password_input:
                self.human_click(password_input)
                time.sleep(random.uniform(0.3, 0.6))
                password_input.clear()
                self.human_type(password_input, password)
                time.sleep(random.uniform(0.5, 1))
            
            # === 3. Điền Số điện thoại ===
            phone_input = self.wait_and_find(By.CSS_SELECTOR, 'input[data-input-name="phone"]')
            if phone_input:
                self.human_click(phone_input)
                time.sleep(random.uniform(0.3, 0.6))
                phone_input.clear()
                # Bỏ số 0 đầu nếu có (vì đã có +84)
                phone_number = phone[1:] if phone.startswith('0') else phone
                self.human_type(phone_input, phone_number)
                time.sleep(random.uniform(0.5, 1))
            
            # === 4. Điền Họ tên ===
            realname_input = self.wait_and_find(By.CSS_SELECTOR, 'input[data-input-name="realName"]')
            if realname_input:
                self.human_click(realname_input)
                time.sleep(random.uniform(0.3, 0.6))
                realname_input.clear()
                self.human_type(realname_input, fullname)
                time.sleep(random.uniform(0.5, 1))
            
            # Di chuột ngẫu nhiên
            self.random_mouse_move()
            
            return True
        except Exception as e:
            print(f"Lỗi điền form: {e}")
            return False
    
    def click_register_button(self):
        """Bấm nút đăng ký - Force click cho React"""
        try:
            time.sleep(random.uniform(0.5, 1))
            
            # Script để force click React button
            react_click_script = """
                function forceClickReact(element) {
                    // Tạo và dispatch các events React cần
                    const events = ['mousedown', 'mouseup', 'click'];
                    
                    events.forEach(eventType => {
                        const event = new MouseEvent(eventType, {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            buttons: 1
                        });
                        element.dispatchEvent(event);
                    });
                    
                    // Trigger React's synthetic event
                    const reactKey = Object.keys(element).find(key => 
                        key.startsWith('__reactFiber$') || 
                        key.startsWith('__reactInternalInstance$') ||
                        key.startsWith('__reactProps$')
                    );
                    
                    if (reactKey && element[reactKey]) {
                        const props = Object.keys(element).find(key => key.startsWith('__reactProps$'));
                        if (props && element[props] && element[props].onClick) {
                            element[props].onClick({
                                preventDefault: () => {},
                                stopPropagation: () => {},
                                target: element,
                                currentTarget: element
                            });
                        }
                    }
                }
                
                // Tìm và click nút đăng ký
                let btn = document.getElementById('insideRegisterSubmitClick');
                if (!btn) {
                    btn = document.querySelector('button.ui-button--primary');
                }
                if (!btn) {
                    btn = document.querySelector('[class*="submitButton"] button');
                }
                if (!btn) {
                    // Tìm theo text
                    const buttons = document.querySelectorAll('button');
                    for (let b of buttons) {
                        if (b.textContent.includes('ĐĂNG KÝ')) {
                            btn = b;
                            break;
                        }
                    }
                }
                
                if (btn) {
                    // Scroll to button
                    btn.scrollIntoView({block: 'center'});
                    
                    // Remove disabled nếu có
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    
                    // Focus
                    btn.focus();
                    
                    // Force click
                    forceClickReact(btn);
                    
                    // Backup: native click
                    setTimeout(() => btn.click(), 100);
                    
                    return true;
                }
                return false;
            """
            
            result = self.driver.execute_script(react_click_script)
            print(f"React force click result: {result}")
            time.sleep(random.uniform(1.5, 2.5))
            return result
            
        except Exception as e:
            print(f"Lỗi click đăng ký: {e}")
            return False
    
    def check_captcha(self):
        """Kiểm tra có captcha không"""
        try:
            # Tìm Geetest captcha container
            captcha = self.driver.find_elements(By.CSS_SELECTOR, '.botion_subitem, .geetest_panel, [class*="botion"], [class*="geetest"]')
            return len(captcha) > 0
        except:
            return False
    
    def get_geetest_captcha_image(self):
        """Lấy ảnh Geetest captcha, lưu temp file và trả về base64"""
        temp_file = None
        try:
            # Chờ captcha xuất hiện
            time.sleep(1)
            
            # Tìm container chứa 9 ô captcha
            captcha_container = None
            selectors = [
                '.botion_subitem',
                '.botion_window',
                '.geetest_item_wrap',
                '[class*="botion_nine"]',
                '[class*="geetest_nine"]'
            ]
            
            for selector in selectors:
                try:
                    captcha_container = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if captcha_container:
                        break
                except:
                    continue
            
            if captcha_container:
                # Tạo temp file
                temp_file = tempfile.NamedTemporaryFile(
                    suffix='.png', 
                    prefix='captcha_', 
                    delete=False
                )
                temp_path = temp_file.name
                temp_file.close()
                
                # Screenshot và lưu vào file
                captcha_container.screenshot(temp_path)
                print(f"Đã lưu captcha vào: {temp_path}")
                
                # Đọc file và convert sang base64
                with open(temp_path, 'rb') as f:
                    image_data = f.read()
                    screenshot_base64 = base64.b64encode(image_data).decode('utf-8')
                
                # Lưu path để xóa sau
                self._temp_captcha_file = temp_path
                
                return screenshot_base64
            
            # Fallback: lấy URL ảnh từ background-image
            img_elements = self.driver.find_elements(By.CSS_SELECTOR, '[class*="botion_item_img"], [class*="geetest_item_img"]')
            if img_elements:
                style = img_elements[0].get_attribute('style')
                if 'url(' in style:
                    import re
                    match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                    if match:
                        return match.group(1)  # Return URL
            
            return None
        except Exception as e:
            print(f"Lỗi lấy ảnh captcha: {e}")
            # Cleanup temp file nếu có lỗi
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.remove(temp_file.name)
                except:
                    pass
            return None
    
    def cleanup_temp_captcha(self):
        """Xóa file captcha tạm"""
        try:
            if hasattr(self, '_temp_captcha_file') and self._temp_captcha_file:
                if os.path.exists(self._temp_captcha_file):
                    os.remove(self._temp_captcha_file)
                    print(f"Đã xóa temp captcha: {self._temp_captcha_file}")
                self._temp_captcha_file = None
        except Exception as e:
            print(f"Lỗi xóa temp file: {e}")
    
    def click_geetest_cells(self, result):
        """
        Click vào các ô captcha theo kết quả
        result có thể là:
            - "1,8,9" (thứ tự ô, index từ 1)
            - "coordinates:x=56,y=99;x=283,y=276" (tọa độ)
        """
        try:
            time.sleep(0.5)
            
            if result.startswith("coordinates:"):
                # Click theo tọa độ
                coords_str = result.replace("coordinates:", "")
                coords = coords_str.split(";")
                
                # Tìm captcha container để lấy offset
                container = self.driver.find_element(By.CSS_SELECTOR, '.botion_window, .botion_subitem, [class*="botion_nine"]')
                container_loc = container.location
                
                for coord in coords:
                    if 'x=' in coord and 'y=' in coord:
                        parts = coord.split(',')
                        x = int(parts[0].split('=')[1])
                        y = int(parts[1].split('=')[1])
                        
                        # Click tại vị trí
                        actions = ActionChains(self.driver)
                        actions.move_to_element_with_offset(container, x, y)
                        time.sleep(random.uniform(0.2, 0.4))
                        actions.click()
                        actions.perform()
                        time.sleep(random.uniform(0.3, 0.6))
            else:
                # Click theo thứ tự ô (1-9)
                cells = result.replace(" ", "").split(",")
                
                for cell_num in cells:
                    if not cell_num.isdigit():
                        continue
                    
                    cell_index = int(cell_num) - 1  # Convert to 0-based
                    
                    # Tìm ô tương ứng
                    cell_selectors = [
                        f'.botion_{cell_index}',
                        f'[class*="botion_{cell_index}"]',
                        f'.botion_item:nth-child({int(cell_num)})',
                        f'.geetest_item:nth-child({int(cell_num)})'
                    ]
                    
                    cell_element = None
                    for selector in cell_selectors:
                        try:
                            cell_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if cell_element:
                                break
                        except:
                            continue
                    
                    if cell_element:
                        # Scroll vào view
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell_element)
                        time.sleep(random.uniform(0.1, 0.2))
                        
                        # Click
                        actions = ActionChains(self.driver)
                        actions.move_to_element(cell_element)
                        time.sleep(random.uniform(0.15, 0.3))
                        actions.click()
                        actions.perform()
                        
                        print(f"Clicked cell {cell_num}")
                        time.sleep(random.uniform(0.4, 0.7))
            
            return True
        except Exception as e:
            print(f"Lỗi click captcha cells: {e}")
            return False
    
    def click_geetest_confirm(self):
        """Bấm nút xác nhận captcha"""
        try:
            time.sleep(0.5)
            
            # Tìm nút confirm
            confirm_selectors = [
                '.botion_submit',
                '.geetest_commit',
                '[class*="botion_submit"]',
                '[class*="geetest_commit"]',
                '[class*="botion_confirm"]',
                'button[class*="submit"]'
            ]
            
            for selector in confirm_selectors:
                try:
                    confirm_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if confirm_btn:
                        self.driver.execute_script("arguments[0].click();", confirm_btn)
                        print("Clicked captcha confirm button")
                        time.sleep(1)
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            print(f"Lỗi click confirm: {e}")
            return False
    
    def solve_geetest_captcha(self, anticaptcha_api):
        """Giải Geetest captcha hoàn chỉnh"""
        try:
            print("Đang xử lý Geetest captcha...")
            
            # Chờ captcha load
            time.sleep(2)
            
            # Lấy ảnh captcha
            captcha_image = self.get_geetest_captcha_image()
            if not captcha_image:
                print("Không lấy được ảnh captcha")
                return False
            
            print("Đã lấy ảnh captcha, đang gửi giải...")
            
            # Gửi giải captcha (dùng geetest2 để nhận thứ tự ô)
            result = anticaptcha_api.solve_geetest_captcha(captcha_image, click_type="geetest2")
            
            if not result.get("success"):
                print(f"Giải captcha thất bại: {result.get('message')}")
                return False
            
            captcha_result = result.get("result", "")
            print(f"Kết quả captcha: {captcha_result}")
            
            # Click vào các ô theo kết quả
            if self.click_geetest_cells(captcha_result):
                time.sleep(0.5)
                # Bấm xác nhận
                self.click_geetest_confirm()
                time.sleep(2)
                return True
            
            return False
        except Exception as e:
            print(f"Lỗi giải Geetest captcha: {e}")
            return False
    
    def get_captcha_image(self):
        """Lấy ảnh captcha (base64) - backward compatible"""
        return self.get_geetest_captcha_image()
    
    def close(self):
        """Đóng browser"""
        if self.driver:
            self.driver.quit()


class DataGenerator:
    """Tạo dữ liệu đăng ký"""
    
    @staticmethod
    def generate_username(fullname):
        """
        Tạo username từ fullName
        Ví dụ: Nguyễn Quang Hà -> hanqcc2k3
        Username phải dưới 12 ký tự
        """
        # Chuyển về không dấu
        fullname = DataGenerator.remove_accents(fullname.lower())
        parts = fullname.split()
        
        if len(parts) >= 2:
            # Lấy tên + 2 ký tự đầu của họ
            first_name = parts[-1][:3]  # Tên, lấy tối đa 3 ký tự
            last_init = parts[0][0] if parts[0] else ""  # Chữ cái đầu họ
            middle_init = parts[1][0] if len(parts) > 2 else ""  # Chữ cái đầu đệm
        else:
            first_name = parts[0][:4] if parts else "user"
            last_init = ""
            middle_init = ""
        
        # Random 2 ký tự
        random_chars = ''.join(random.choices(string.ascii_lowercase, k=2))
        
        # Random năm sinh (90-05)
        year = random.randint(90, 99) if random.random() > 0.5 else random.randint(0, 5)
        year_str = str(year).zfill(2)
        
        # Ghép username
        username = f"{first_name}{last_init}{middle_init}{random_chars}{year_str}"
        
        # Đảm bảo dưới 12 ký tự
        if len(username) > 11:
            username = username[:11]
        
        return username.lower()
    
    @staticmethod
    def generate_password(username):
        """
        Tạo password từ username
        Password = 'A' + username
        Password phải dưới 12 ký tự
        """
        password = f"A{username}"
        if len(password) > 11:
            password = password[:11]
        return password
    
    @staticmethod
    def remove_accents(text):
        """Xóa dấu tiếng Việt"""
        accents = {
            'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
            'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
            'đ': 'd',
            'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
            'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
            'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
            'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
            'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
        }
        result = ""
        for char in text:
            result += accents.get(char, char)
        return result


class BankDataManager:
    """Quản lý dữ liệu bank - Thread-safe"""
    
    def __init__(self, file_path):
        self.file_path = file_path
    
    def get_next_bank_data(self):
        """
        Lấy dòng bank data tiếp theo chưa được sử dụng
        Format: banknumber|fullName
        Sau khi lấy sẽ thêm |f168 vào cuối để đánh dấu đã sử dụng
        Thread-safe với lock
        """
        with bank_lock:
            if not os.path.exists(self.file_path):
                return None
            
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                selected_line = None
                selected_index = -1
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if line and not line.endswith('|f168'):
                        selected_line = line
                        selected_index = i
                        break
                
                if selected_line is None:
                    return None
                
                # Đánh dấu đã sử dụng
                lines[selected_index] = selected_line + '|f168\n'
                
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                
                # Parse data
                parts = selected_line.split('|')
                if len(parts) >= 2:
                    return {
                        "bank_number": parts[0].strip(),
                        "fullname": parts[1].strip()
                    }
                return None
                
            except Exception as e:
                print(f"Lỗi đọc file bank: {e}")
                return None
    
    def get_remaining_count(self):
        """Đếm số dòng còn lại chưa sử dụng"""
        with bank_lock:
            if not os.path.exists(self.file_path):
                return 0
            
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                count = 0
                for line in lines:
                    line = line.strip()
                    if line and not line.endswith('|f168'):
                        count += 1
                return count
            except:
                return 0


class F1686SRegisterApp:
    """GUI Application - Multi-threaded"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("F1686S Auto Register Tool - Antidetect Multi-Thread")
        self.root.geometry("950x850")
        self.root.resizable(True, True)
        
        self.is_running = False
        self.stop_flag = False
        self.current_browsers = []  # List browsers cho multi-thread
        self.thread_pool = None
        self.current_count = 0
        self.success_count = 0
        
        self.load_config()
        self.create_gui()
    
    def load_config(self):
        """Load config từ file"""
        self.config = {
            "fproxy_keys": "",  # Nhiều key, mỗi dòng 1 key
            "anticaptcha_key": "",
            "viotp_key": "",
            "viotp_service_id": "",
            "bank_data_path": "",
            "account_count": 0,
            "thread_count": 1,  # Số luồng
            "delay_min": 5,
            "delay_max": 10
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
            except:
                pass
    
    def save_config(self):
        """Lưu config vào file"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Lỗi lưu config: {e}")
    
    def create_gui(self):
        """Tạo giao diện"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === Config Frame ===
        config_frame = ttk.LabelFrame(main_frame, text="Cấu hình API", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # FProxy Keys (nhiều key)
        ttk.Label(config_frame, text="FProxy API Keys:").grid(row=0, column=0, sticky=tk.NW, pady=2)
        fproxy_frame = ttk.Frame(config_frame)
        fproxy_frame.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        
        self.fproxy_text = tk.Text(fproxy_frame, width=55, height=4)
        self.fproxy_text.pack(side=tk.LEFT)
        fproxy_scroll = ttk.Scrollbar(fproxy_frame, orient=tk.VERTICAL, command=self.fproxy_text.yview)
        fproxy_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.fproxy_text.config(yscrollcommand=fproxy_scroll.set)
        self.fproxy_text.insert("1.0", self.config.get("fproxy_keys", ""))
        
        ttk.Label(config_frame, text="(Mỗi dòng 1 key,\nsố key = số luồng)", font=('Arial', 8)).grid(row=0, column=2, padx=5)
        
        # Anticaptcha Key
        ttk.Label(config_frame, text="Anticaptcha.top Key:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.anticaptcha_entry = ttk.Entry(config_frame, width=60)
        self.anticaptcha_entry.grid(row=1, column=1, padx=5, pady=2)
        self.anticaptcha_entry.insert(0, self.config.get("anticaptcha_key", ""))
        
        # ViOTP Key
        ttk.Label(config_frame, text="ViOTP Token:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.viotp_entry = ttk.Entry(config_frame, width=60)
        self.viotp_entry.grid(row=2, column=1, padx=5, pady=2)
        self.viotp_entry.insert(0, self.config.get("viotp_key", ""))
        
        # ViOTP Service ID
        ttk.Label(config_frame, text="ViOTP Service ID:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.service_id_entry = ttk.Entry(config_frame, width=20)
        self.service_id_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        self.service_id_entry.insert(0, self.config.get("viotp_service_id", ""))
        
        # === Data Frame ===
        data_frame = ttk.LabelFrame(main_frame, text="Dữ liệu Bank", padding="10")
        data_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(data_frame, text="File Bank Data:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.bank_path_entry = ttk.Entry(data_frame, width=50)
        self.bank_path_entry.grid(row=0, column=1, padx=5, pady=2)
        self.bank_path_entry.insert(0, self.config.get("bank_data_path", ""))
        
        ttk.Button(data_frame, text="Browse", command=self.browse_bank_file).grid(row=0, column=2, padx=5)
        
        self.bank_count_label = ttk.Label(data_frame, text="Còn lại: 0 dòng")
        self.bank_count_label.grid(row=0, column=3, padx=10)
        
        # === Settings Frame ===
        settings_frame = ttk.LabelFrame(main_frame, text="Cài đặt chạy", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(settings_frame, text="Số tài khoản (0 = vô hạn):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.account_count_entry = ttk.Entry(settings_frame, width=10)
        self.account_count_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        self.account_count_entry.insert(0, str(self.config.get("account_count", 0)))
        
        ttk.Label(settings_frame, text="Số luồng:").grid(row=0, column=2, padx=(20, 5), sticky=tk.W)
        self.thread_count_entry = ttk.Entry(settings_frame, width=5)
        self.thread_count_entry.grid(row=0, column=3, padx=2)
        self.thread_count_entry.insert(0, str(self.config.get("thread_count", 1)))
        
        ttk.Label(settings_frame, text="Delay (giây):").grid(row=0, column=4, padx=(20, 5), sticky=tk.W)
        self.delay_min_entry = ttk.Entry(settings_frame, width=5)
        self.delay_min_entry.grid(row=0, column=5, padx=2)
        self.delay_min_entry.insert(0, str(self.config.get("delay_min", 5)))
        
        ttk.Label(settings_frame, text="-").grid(row=0, column=6)
        self.delay_max_entry = ttk.Entry(settings_frame, width=5)
        self.delay_max_entry.grid(row=0, column=7, padx=2)
        self.delay_max_entry.insert(0, str(self.config.get("delay_max", 10)))
        
        # === Control Buttons ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ BẮT ĐẦU", command=self.start_process)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ DỪNG", command=self.stop_process, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="💾 Lưu Config", command=self.save_all_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 Refresh Bank", command=self.refresh_bank_count).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🧪 Test Proxy", command=self.test_proxy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📱 Test ViOTP", command=self.test_viotp).pack(side=tk.LEFT, padx=5)
        
        # === Status Frame ===
        status_frame = ttk.LabelFrame(main_frame, text="Trạng thái hiện tại", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_label = ttk.Label(status_frame, text="Sẵn sàng", font=('Arial', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT)
        
        self.thread_status_label = ttk.Label(status_frame, text="Luồng: 0 đang chạy")
        self.thread_status_label.pack(side=tk.LEFT, padx=20)
        
        self.progress_label = ttk.Label(status_frame, text="0/0 tài khoản | Thành công: 0")
        self.progress_label.pack(side=tk.RIGHT)
        
        # === Log Frame ===
        log_frame = ttk.LabelFrame(main_frame, text="Log (Multi-thread)", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Config tags for colored log
        self.log_text.tag_config("thread0", foreground="#0066CC")
        self.log_text.tag_config("thread1", foreground="#009933")
        self.log_text.tag_config("thread2", foreground="#CC6600")
        self.log_text.tag_config("thread3", foreground="#9933CC")
        self.log_text.tag_config("thread4", foreground="#CC0066")
        self.log_text.tag_config("error", foreground="#CC0000")
        self.log_text.tag_config("success", foreground="#009900")
        
        # === Result Frame ===
        result_frame = ttk.LabelFrame(main_frame, text="Kết quả (username|password|phone|bank|fullname)", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=8, wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # Initial refresh
        self.refresh_bank_count()
    
    def browse_bank_file(self):
        """Chọn file bank data"""
        file_path = filedialog.askopenfilename(
            title="Chọn file Bank Data",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.bank_path_entry.delete(0, tk.END)
            self.bank_path_entry.insert(0, file_path)
            self.refresh_bank_count()
    
    def refresh_bank_count(self):
        """Cập nhật số lượng bank còn lại"""
        path = self.bank_path_entry.get().strip()
        if path:
            manager = BankDataManager(path)
            count = manager.get_remaining_count()
            self.bank_count_label.config(text=f"Còn lại: {count} dòng")
        else:
            self.bank_count_label.config(text="Còn lại: 0 dòng")
    
    def save_all_config(self):
        """Lưu tất cả config"""
        self.config["fproxy_keys"] = self.fproxy_text.get("1.0", tk.END).strip()
        self.config["anticaptcha_key"] = self.anticaptcha_entry.get().strip()
        self.config["viotp_key"] = self.viotp_entry.get().strip()
        self.config["viotp_service_id"] = self.service_id_entry.get().strip()
        self.config["bank_data_path"] = self.bank_path_entry.get().strip()
        
        try:
            self.config["account_count"] = int(self.account_count_entry.get() or 0)
        except:
            self.config["account_count"] = 0
        
        try:
            self.config["thread_count"] = int(self.thread_count_entry.get() or 1)
        except:
            self.config["thread_count"] = 1
        
        try:
            self.config["delay_min"] = int(self.delay_min_entry.get() or 5)
            self.config["delay_max"] = int(self.delay_max_entry.get() or 10)
        except:
            self.config["delay_min"] = 5
            self.config["delay_max"] = 10
        
        self.save_config()
        self.log("✅ Đã lưu config!")
        messagebox.showinfo("Thành công", "Đã lưu cấu hình!")
    
    def get_fproxy_keys(self):
        """Lấy danh sách FProxy keys"""
        text = self.fproxy_text.get("1.0", tk.END).strip()
        keys = [k.strip() for k in text.split('\n') if k.strip()]
        return keys
    
    def log(self, message, thread_id=None):
        """Ghi log - Thread-safe"""
        def do_log():
            with log_lock:
                timestamp = datetime.now().strftime("%H:%M:%S")
                if thread_id is not None:
                    prefix = f"[{timestamp}][T{thread_id}] "
                    tag = f"thread{thread_id % 5}"
                else:
                    prefix = f"[{timestamp}] "
                    tag = None
                
                log_message = f"{prefix}{message}\n"
                
                if tag:
                    self.log_text.insert(tk.END, log_message, tag)
                else:
                    # Check for error/success
                    if "❌" in message or "Lỗi" in message:
                        self.log_text.insert(tk.END, log_message, "error")
                    elif "✅" in message or "Thành công" in message:
                        self.log_text.insert(tk.END, log_message, "success")
                    else:
                        self.log_text.insert(tk.END, log_message)
                
                self.log_text.see(tk.END)
        
        # Schedule in main thread
        self.root.after(0, do_log)
    
    def add_result(self, result):
        """Thêm kết quả - Thread-safe"""
        def do_add():
            with result_lock:
                self.result_text.insert(tk.END, result + "\n")
                self.result_text.see(tk.END)
                
                # Lưu vào file
                try:
                    with open("results.txt", "a", encoding="utf-8") as f:
                        f.write(result + "\n")
                except:
                    pass
        
        self.root.after(0, do_add)
    
    def update_status(self, status):
        """Cập nhật trạng thái"""
        def do_update():
            self.status_label.config(text=status)
        self.root.after(0, do_update)
    
    def update_progress(self):
        """Cập nhật tiến độ - Thread-safe"""
        def do_update():
            try:
                account_count = int(self.account_count_entry.get() or 0)
            except:
                account_count = 0
            
            total_str = str(account_count) if account_count > 0 else "∞"
            self.progress_label.config(
                text=f"{self.current_count}/{total_str} tài khoản | Thành công: {self.success_count}"
            )
        self.root.after(0, do_update)
    
    def update_thread_status(self, active_count):
        """Cập nhật số luồng đang chạy"""
        def do_update():
            self.thread_status_label.config(text=f"Luồng: {active_count} đang chạy")
        self.root.after(0, do_update)
    
    def test_proxy(self):
        """Test xoay proxy - test tất cả keys"""
        keys = self.get_fproxy_keys()
        if not keys:
            messagebox.showerror("Lỗi", "Vui lòng nhập ít nhất 1 FProxy API Key!")
            return
        
        self.log(f"🔄 Đang test {len(keys)} proxy key(s)...")
        
        def do_test():
            for i, key in enumerate(keys):
                fproxy = FProxyAPI(key)
                result = fproxy.get_new_proxy()
                
                if result["success"]:
                    self.log(f"✅ Key {i+1}: {result['proxy']} ({result.get('location', 'N/A')})", i)
                else:
                    self.log(f"❌ Key {i+1}: {result['message']}", i)
                
                time.sleep(1)  # Tránh spam API
        
        threading.Thread(target=do_test, daemon=True).start()
    
    def test_viotp(self):
        """Test ViOTP"""
        token = self.viotp_entry.get().strip()
        if not token:
            messagebox.showerror("Lỗi", "Vui lòng nhập ViOTP Token!")
            return
        
        self.log("📱 Đang test ViOTP...")
        
        def do_test():
            viotp = ViOTPAPI(token)
            result = viotp.get_balance()
            
            if result["success"]:
                self.log(f"✅ Số dư ViOTP: {result['balance']:,}đ")
            else:
                self.log(f"❌ Lỗi: {result['message']}")
        
        threading.Thread(target=do_test, daemon=True).start()
    
    def start_process(self):
        """Bắt đầu quá trình đăng ký - Multi-thread"""
        # Validate
        fproxy_keys = self.get_fproxy_keys()
        if not fproxy_keys:
            messagebox.showerror("Lỗi", "Vui lòng nhập ít nhất 1 FProxy API Key!")
            return
        if not self.viotp_entry.get().strip():
            messagebox.showerror("Lỗi", "Vui lòng nhập ViOTP Token!")
            return
        if not self.service_id_entry.get().strip():
            messagebox.showerror("Lỗi", "Vui lòng nhập ViOTP Service ID!")
            return
        if not self.bank_path_entry.get().strip():
            messagebox.showerror("Lỗi", "Vui lòng chọn file Bank Data!")
            return
        
        # Save config
        self.save_all_config()
        
        # Reset counters
        self.current_count = 0
        self.success_count = 0
        self.is_running = True
        self.stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Reset window positions
        WindowManager.reset_positions()
        
        # Số luồng = số key FProxy
        thread_count = len(fproxy_keys)
        self.log(f"🚀 Khởi động {thread_count} luồng với {thread_count} proxy key(s)...")
        
        # Start worker threads
        threading.Thread(target=self.start_workers, args=(fproxy_keys,), daemon=True).start()
    
    def stop_process(self):
        """Dừng quá trình"""
        self.stop_flag = True
        self.log("⏹ Đang dừng tất cả luồng...")
        
        # Close all browsers
        for browser in self.current_browsers:
            try:
                browser.close()
            except:
                pass
        self.current_browsers.clear()
    
    def start_workers(self, fproxy_keys):
        """Khởi động các worker threads"""
        try:
            account_count = int(self.account_count_entry.get() or 0)
        except:
            account_count = 0
        
        thread_count = len(fproxy_keys)
        threads = []
        
        # Tạo và start các threads
        for i, key in enumerate(fproxy_keys):
            t = threading.Thread(
                target=self.worker_thread,
                args=(i, key, account_count),
                daemon=True
            )
            threads.append(t)
            t.start()
            self.log(f"▶ Luồng {i} đã khởi động với proxy key", i)
            time.sleep(0.5)  # Stagger start
        
        self.update_thread_status(thread_count)
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Cleanup
        self.is_running = False
        self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
        self.update_status("Đã dừng")
        self.update_thread_status(0)
        self.log("✅ Tất cả luồng đã hoàn thành!")
    
    def worker_thread(self, thread_id, fproxy_key, account_count):
        """Worker thread cho mỗi luồng đăng ký"""
        # Init APIs
        fproxy = FProxyAPI(fproxy_key)
        viotp = ViOTPAPI(self.config["viotp_key"])
        bank_manager = BankDataManager(self.config["bank_data_path"])
        
        while not self.stop_flag:
            # Check global limit
            with counter_lock:
                if account_count > 0 and self.current_count >= account_count:
                    self.log(f"Đã đạt giới hạn {account_count} tài khoản", thread_id)
                    break
            
            try:
                # === Step 1: Lấy bank data ===
                self.log("📋 Đang lấy bank data...", thread_id)
                
                bank_data = bank_manager.get_next_bank_data()
                if not bank_data:
                    self.log("❌ Hết bank data!", thread_id)
                    break
                
                fullname = bank_data["fullname"]
                bank_number = bank_data["bank_number"]
                self.log(f"Bank: {bank_number} - {fullname}", thread_id)
                
                # === Step 2: Generate username/password ===
                username = DataGenerator.generate_username(fullname)
                password = DataGenerator.generate_password(username)
                self.log(f"User: {username} | Pass: {password}", thread_id)
                
                # === Step 3: Xoay proxy ===
                self.log("🔄 Đang xoay proxy...", thread_id)
                
                proxy_result = fproxy.get_new_proxy()
                retry_count = 0
                while not proxy_result["success"] and retry_count < 3:
                    wait_time = 30 + retry_count * 10
                    self.log(f"⏳ Chờ {wait_time}s xoay proxy...", thread_id)
                    time.sleep(wait_time)
                    proxy_result = fproxy.get_new_proxy()
                    retry_count += 1
                
                if proxy_result["success"]:
                    proxy = proxy_result["http"]
                    proxy_user = proxy_result.get("user")
                    proxy_pass = proxy_result.get("pass")
                    self.log(f"✅ Proxy: {proxy} ({proxy_result.get('location', 'N/A')})", thread_id)
                else:
                    self.log(f"⚠ Không có proxy, tiếp tục...", thread_id)
                    proxy = None
                    proxy_user = None
                    proxy_pass = None
                
                # === Step 4: Lấy số điện thoại ===
                self.log("📱 Đang thuê số điện thoại...", thread_id)
                
                phone_result = viotp.request_phone(self.config["viotp_service_id"])
                if not phone_result["success"]:
                    self.log(f"❌ Lỗi thuê số: {phone_result['message']}", thread_id)
                    time.sleep(5)
                    continue
                
                phone = "0" + phone_result["phone"]
                request_id = phone_result["request_id"]
                self.log(f"✅ Phone: {phone} (ID: {request_id})", thread_id)
                
                # === Step 5: Tạo result data ===
                result_data = f"{username}|{password}|{phone}|{bank_number}|{fullname}"
                self.log(f"📝 Data: {result_data}", thread_id)
                
                # === Step 6: Mở browser và đăng ký ===
                self.log("🌐 Đang mở browser antidetect...", thread_id)
                
                browser = AntidetectBrowser(proxy=proxy, proxy_user=proxy_user, proxy_pass=proxy_pass, thread_id=thread_id)
                self.current_browsers.append(browser)
                
                try:
                    driver = browser.create_browser()
                    self.log("✅ Browser đã khởi tạo!", thread_id)
                    
                    # Mở trang đăng ký
                    self.log("🔗 Đang mở trang đăng ký...", thread_id)
                    driver.get("https://f1686s.com/home/register")
                    
                    # Random delay
                    time.sleep(random.uniform(3, 5))
                    browser.random_mouse_move()
                    
                    self.log("📝 Đang điền form đăng ký...", thread_id)
                    
                    # Điền form đăng ký
                    fill_success = browser.fill_registration_form(
                        username=username,
                        password=password,
                        phone=phone,
                        fullname=fullname
                    )
                    
                    if fill_success:
                        self.log("✅ Đã điền xong form!", thread_id)
                        
                        # Bấm nút đăng ký
                        time.sleep(random.uniform(1, 2))
                        self.log("🖱️ Đang bấm nút Đăng Ký...", thread_id)
                        
                        click_success = browser.click_register_button()
                        if click_success:
                            self.log("✅ Đã bấm đăng ký!", thread_id)
                            
                            # Chờ và kiểm tra captcha
                            time.sleep(2)
                            if browser.check_captcha():
                                self.log("🔐 Phát hiện Geetest Captcha, đang giải...", thread_id)
                                
                                # Init anticaptcha API
                                anticaptcha = AnticaptchaAPI(self.config["anticaptcha_key"])
                                
                                # Giải captcha
                                captcha_solved = browser.solve_geetest_captcha(anticaptcha)
                                
                                if captcha_solved:
                                    self.log("✅ Đã giải captcha thành công!", thread_id)
                                else:
                                    self.log("❌ Giải captcha thất bại!", thread_id)
                            else:
                                self.log("ℹ️ Không có captcha", thread_id)
                        else:
                            self.log("⚠️ Không bấm được nút đăng ký", thread_id)
                    else:
                        self.log("❌ Lỗi điền form!", thread_id)
                    
                    # Thêm kết quả
                    self.add_result(result_data)
                    
                    with counter_lock:
                        self.current_count += 1
                        self.success_count += 1
                    
                    self.update_progress()
                    self.root.after(0, self.refresh_bank_count)
                    
                    # Chờ để xem kết quả
                    self.log("⏳ Chờ 30s xem kết quả...", thread_id)
                    for i in range(30):
                        if self.stop_flag:
                            break
                        time.sleep(1)
                    
                except Exception as e:
                    self.log(f"❌ Lỗi browser: {e}", thread_id)
                finally:
                    browser.close()
                    if browser in self.current_browsers:
                        self.current_browsers.remove(browser)
                    self.log("🔒 Đã đóng browser", thread_id)
                
                # Delay giữa các lần
                if not self.stop_flag:
                    delay = random.randint(
                        self.config.get("delay_min", 5),
                        self.config.get("delay_max", 10)
                    )
                    self.log(f"⏳ Chờ {delay}s...", thread_id)
                    time.sleep(delay)
                
            except Exception as e:
                self.log(f"❌ Lỗi: {e}", thread_id)
                time.sleep(5)
        
        self.log(f"🏁 Luồng {thread_id} kết thúc", thread_id)


def main():
    root = tk.Tk()
    app = F1686SRegisterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
