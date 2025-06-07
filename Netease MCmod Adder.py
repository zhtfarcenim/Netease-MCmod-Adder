import os
import shutil
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, ttk, simpledialog
from tkinter.font import Font
import psutil

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    root = TkinterDnD.Tk()
    dnd_supported = True
except ImportError:
    root = tk.Tk()
    dnd_supported = False

class MCModManager:
    def __init__(self, root):
        self.root = root
        self.root.title("MC Mod 智能模组添加器")
        self.root.geometry("850x650")
        
        self.mods_path = ""
        self.backup_dir = ""
        self.is_replacing = False
        self.is_waiting_for_mc = False
        self.replace_thread = None
        self.replaced_files = set()
        self.used_import_files = set()
        
        self.create_widgets()
        
        if dnd_supported:
            self.setup_drag_drop()
        else:
            self.status_var.set("提示: 拖拽功能需要安装 tkinterdnd2 (pip install tkinterdnd2)")

    def create_widgets(self):
        frame_path = tk.Frame(self.root)
        frame_path.pack(pady=10, padx=10, fill=tk.X)
        
        tk.Label(frame_path, text="MCLauncher路径:").pack(side=tk.LEFT)
        
        self.entry_path = tk.Entry(frame_path, width=50)
        self.entry_path.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        self.entry_path.bind("<FocusOut>", lambda e: self.auto_locate_mods())
        
        tk.Button(frame_path, text="浏览...", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_path, text="定位mods", command=self.locate_mods_folder).pack(side=tk.LEFT)
        
        self.label_mods_path = tk.Label(self.root, text="mods路径: 未定位", 
                                      fg="blue", font=Font(size=9), wraplength=800, justify=tk.LEFT)
        self.label_mods_path.pack(pady=5)
        
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
        
        frame_import = tk.LabelFrame(self.root, text="拖拽或导入JAR文件 (将智能替换未处理过的非@0文件)", padx=5, pady=5)
        frame_import.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        self.file_listbox = tk.Listbox(frame_import, height=15)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.listbox_menu = tk.Menu(self.root, tearoff=0)
        self.listbox_menu.add_command(label="删除选中", command=self.delete_selected)
        self.listbox_menu.add_command(label="清空列表", command=self.clear_list)
        self.file_listbox.bind("<Button-3>", self.show_listbox_menu)
        
        scrollbar = tk.Scrollbar(self.file_listbox)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.file_listbox.yview)
        
        button_frame = tk.Frame(frame_import)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(button_frame, text="添加文件", command=self.add_files).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="添加文件夹", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="批量导入", command=self.batch_import).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="删除选中", command=self.delete_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="清空列表", command=self.clear_list).pack(side=tk.LEFT, padx=5)
        
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(pady=10, fill=tk.X)
        
        self.btn_replace = tk.Button(bottom_frame, text="开始智能替换 (将备份原文件)", 
                                   state=tk.DISABLED, bg="#f44336", fg="white",
                                   command=self.toggle_replacement)
        self.btn_replace.pack(pady=5, ipadx=20)
        
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, 
                anchor=tk.W, fg="gray").pack(side=tk.BOTTOM, fill=tk.X)

    def show_listbox_menu(self, event):
        try:
            self.listbox_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.listbox_menu.grab_release()

    def delete_selected(self):
        selected = self.file_listbox.curselection()
        if not selected:
            messagebox.showwarning("警告", "请先选择要删除的文件")
            return
        
        for i in reversed(selected):
            self.file_listbox.delete(i)
        
        self.check_replace_button_state()
        self.status_var.set(f"已删除 {len(selected)} 个文件")

    def setup_drag_drop(self):
        def handle_drop(event):
            files = self.root.tk.splitlist(event.data)
            added_files = []
            for file in files:
                file = file.strip('{}')
                if os.path.exists(file) and file.lower().endswith('.jar'):
                    self.file_listbox.insert(tk.END, file)
                    added_files.append(file)
            if added_files:
                self.check_replace_button_state()
                self.status_var.set(f"拖拽添加了 {len(added_files)} 个文件")
        
        try:
            self.file_listbox.drop_target_register(DND_FILES)
            self.file_listbox.dnd_bind('<<Drop>>', handle_drop)
        except Exception as e:
            self.status_var.set(f"拖拽功能初始化失败: {str(e)}")

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, path)
            self.auto_locate_mods()

    def locate_mods_folder(self):
        user_path = self.entry_path.get().strip()
        
        if not user_path:
            messagebox.showerror("错误", "请输入MCLauncher路径")
            return
        
        if not self.auto_locate_mods():
            mods_path = simpledialog.askstring(
                "手动输入",
                "自动定位失败，请输入mods文件夹完整路径:",
                parent=self.root
            )
            if mods_path and os.path.exists(mods_path):
                self.mods_path = mods_path
                self.label_mods_path.config(text=f"mods路径: {self.mods_path}", fg="blue")
                self.status_var.set(f"已手动设置mods文件夹: {self.mods_path}")
                self.check_replace_button_state()
            else:
                self.label_mods_path.config(text="mods路径: 无效路径", fg="red")
                self.status_var.set("错误: 提供的mods路径无效")

    def auto_locate_mods(self):
        user_path = self.entry_path.get().strip()
        
        if not user_path:
            return False
        
        mc_launcher_path = self.find_folder_in_path(user_path, "MCLauncher")
        if not mc_launcher_path:
            self.label_mods_path.config(text="mods路径: 未找到MCLauncher文件夹", fg="red")
            self.status_var.set("错误: 路径中未找到MCLauncher文件夹")
            return False
        
        parent_dir = os.path.dirname(mc_launcher_path) or mc_launcher_path
        
        mcl_download_path = os.path.join(parent_dir, "MCLDownload")
        if not os.path.exists(mcl_download_path):
            self.label_mods_path.config(text="mods路径: 未找到MCLDownload文件夹", fg="red")
            self.status_var.set(f"错误: 在上级目录中未找到MCLDownload文件夹\n上级目录: {parent_dir}")
            return False
        
        self.mods_path = os.path.join(mcl_download_path, "Game", ".minecraft", "mods")
        
        if not os.path.exists(self.mods_path):
            self.label_mods_path.config(text=f"mods路径: {self.mods_path}\n(文件夹不存在)", fg="orange")
            self.status_var.set(f"警告: mods文件夹不存在 - {self.mods_path}")
            self.mods_path = ""
            return False
        else:
            self.label_mods_path.config(text=f"mods路径: {self.mods_path}", fg="blue")
            self.status_var.set(f"已定位mods文件夹: {self.mods_path}")
            self.check_replace_button_state()
            return True

    def find_folder_in_path(self, path, folder_name):
        normalized_path = os.path.normpath(path)
        parts = normalized_path.split(os.sep)
        
        for i, part in enumerate(parts):
            if part.lower() == folder_name.lower():
                return os.sep.join(parts[:i+1])
        
        return None

    def batch_import(self):
        files = filedialog.askopenfilenames(
            title="选择多个JAR文件",
            filetypes=[("JAR文件", "*.jar"), ("所有文件", "*.*")]
        )
        
        if files:
            self.add_files_to_list(files)
            self.status_var.set(f"批量导入 {len(files)} 个文件")

    def add_files_to_list(self, files):
        for file in files:
            if file.lower().endswith('.jar'):
                self.file_listbox.insert(tk.END, file)
            else:
                messagebox.showwarning("警告", f"忽略非JAR文件: {os.path.basename(file)}")
        self.check_replace_button_state()

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="选择JAR文件",
            filetypes=[("JAR文件", "*.jar"), ("所有文件", "*.*")]
        )
        if files:
            self.add_files_to_list(files)
            self.status_var.set(f"添加 {len(files)} 个文件到列表")

    def add_folder(self):
        folder = filedialog.askdirectory(title="选择包含JAR文件的文件夹")
        if not folder:
            return
        
        added_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith('.jar'):
                    full_path = os.path.join(root, file)
                    added_files.append(full_path)
        
        if added_files:
            self.add_files_to_list(added_files)
            self.status_var.set(f"从文件夹添加了 {len(added_files)} 个JAR文件")
        else:
            messagebox.showinfo("提示", "所选文件夹中没有找到JAR文件")

    def clear_list(self):
        self.file_listbox.delete(0, tk.END)
        self.used_import_files = set()
        self.check_replace_button_state()
        self.status_var.set("已清空文件列表")

    def check_replace_button_state(self):
        if self.mods_path and self.file_listbox.size() > 0:
            self.btn_replace.config(state=tk.NORMAL)
        else:
            self.btn_replace.config(state=tk.DISABLED)
            if self.is_replacing:
                self.stop_replacement()

    def create_backup(self):
        backup_dir = os.path.join(os.path.dirname(self.mods_path), "mods_backup")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        for file in os.listdir(backup_dir):
            try:
                os.remove(os.path.join(backup_dir, file))
            except:
                pass
        
        for file in os.listdir(self.mods_path):
            if file.endswith('.jar'):
                src = os.path.join(self.mods_path, file)
                dst = os.path.join(backup_dir, file)
                shutil.copy2(src, dst)
        
        return backup_dir

    def find_non_zero_files(self):
        non_zero_files = []
        for file in os.listdir(self.mods_path):
            if (file.endswith('.jar') and 
                not file.endswith('@0.jar') and 
                file not in self.replaced_files):
                non_zero_files.append(file)
        return non_zero_files

    def is_minecraft_running(self):
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == 'javaw.exe':
                return True
        return False

    def replacement_loop(self):
        self.is_waiting_for_mc = True
        self.status_var.set("等待Minecraft启动...")
        
        while self.is_replacing and not self.is_minecraft_running():
            time.sleep(0.05)
        
        if not self.is_replacing:
            return

        self.status_var.set("检测到Minecraft，等待1秒后开始替换...")
        time.sleep(1)
            
        self.is_waiting_for_mc = False
        self.status_var.set("开始执行文件替换...")
        
        try:
            import_files = [self.file_listbox.get(i) for i in range(self.file_listbox.size())]
            target_files = [f for f in os.listdir(self.mods_path) 
                          if f.endswith('.jar') and not f.endswith('@0.jar')]
            
            if not import_files:
                self.status_var.set("错误：没有可用的替换文件")
                return

            os.makedirs(self.backup_dir, exist_ok=True)

            replaced_count = 0
            for i in range(min(len(import_files), len(target_files))):
                if not self.is_replacing:
                    break
                
                src_path = import_files[i]
                target_name = target_files[i]
                dest_path = os.path.join(self.mods_path, target_name)
                backup_path = os.path.join(self.backup_dir, target_name)

                try:
                    if os.path.exists(dest_path) and not os.path.exists(backup_path):
                        shutil.copy2(dest_path, backup_path)
                    
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    
                    shutil.copy2(src_path, dest_path)
                    
                    if os.path.getsize(src_path) != os.path.getsize(dest_path):
                        raise Exception("文件大小不一致，替换可能失败")
                    
                    replaced_count += 1
                    self.status_var.set(
                        f"已替换: {target_name} (进度: {i+1}/{len(target_files)})"
                    )
                    self.root.update()
                    
                except Exception as e:
                    self.status_var.set(f"替换失败 {target_name}: {str(e)}")
                    continue

                time.sleep(0.05)

            self.status_var.set(f"替换完成！共替换 {replaced_count} 个文件")
            
        except Exception as e:
            self.status_var.set(f"替换过程出错: {str(e)}")
        finally:
            self.stop_replacement()

    def start_replacement(self):
        if not self.mods_path:
            messagebox.showerror("错误", "mods路径未设置")
            return
        
        if not os.path.exists(self.mods_path):
            messagebox.showerror("错误", f"mods文件夹不存在:\n{self.mods_path}")
            return
        
        if self.file_listbox.size() == 0:
            messagebox.showwarning("警告", "没有要导入的文件")
            return
        
        try:
            self.backup_dir = os.path.join(os.path.dirname(self.mods_path), "mods_backup")
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
        except Exception as e:
            messagebox.showerror("备份错误", f"创建备份文件夹失败: {e}")
            return
        
        self.replaced_files = set()
        self.is_replacing = True

        self.replace_thread = threading.Thread(target=self.replacement_loop, daemon=True)
        self.replace_thread.start()

    def stop_replacement(self):
        self.is_replacing = False
        self.is_waiting_for_mc = False
        self.btn_replace.config(text="开始智能替换", bg="#f44336")
        
        if self.replace_thread and self.replace_thread.is_alive():
            self.replace_thread.join(timeout=0.1)

    def toggle_replacement(self):
        if self.is_replacing:
            self.stop_replacement()
        else:
            self.start_replacement()

if __name__ == "__main__":
    if not dnd_supported:
        def show_dnd_warning():
            messagebox.showwarning("功能限制", 
                "拖拽功能需要安装 tkinterdnd2 库:\n"
                "pip install tkinterdnd2\n\n"
                "您仍然可以使用按钮导入文件")
        root.after(100, show_dnd_warning)
    
    app = MCModManager(root)
    root.mainloop()
