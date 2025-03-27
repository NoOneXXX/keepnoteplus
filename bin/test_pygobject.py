import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

# 定义窗口类，继承自 Gtk.Window
class MyWindow(Gtk.Window):
    def __init__(self):
        # 调用父类的构造函数，设置窗口标题
        super().__init__(title="Simple Window with Button")

        # 设置窗口默认大小
        self.set_default_size(400, 300)

        # 创建一个按钮
        self.button = Gtk.Button(label="Click Me!")
        # 连接按钮的 "clicked" 信号到回调函数
        self.button.connect("clicked", self.on_button_clicked)

        # 将按钮添加到窗口
        self.add(self.button)

        # 连接窗口的 "destroy" 信号，点击关闭按钮时退出程序
        self.connect("destroy", Gtk.main_quit)

    # 按钮点击时的回调函数
    def on_button_clicked(self, widget):
        print("Button was clicked!")

# 主函数
def main():
    # 创建窗口实例
    window = MyWindow()
    # 显示窗口及其所有子控件
    window.show_all()
    # 进入 GTK 主循环
    Gtk.main()

if __name__ == "__main__":
    main()