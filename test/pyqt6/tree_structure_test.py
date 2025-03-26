import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter, QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt


class NotesApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQt6 Notes Sample with Tree Lines")
        self.setGeometry(100, 100, 800, 600)

        # Create the main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Tree view
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Notes Categories")
        self.tree.setColumnCount(1)

        # Enable lines in the tree view
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(20)
        self.tree.setUniformRowHeights(True)

        self.add_tree_items(self.tree)
        self.tree.itemClicked.connect(self.on_tree_item_clicked)

        # Right panel: Text editor
        self.editor = QTextEdit()

        # Add widgets to splitter
        splitter.addWidget(self.tree)
        splitter.addWidget(self.editor)
        splitter.setSizes([200, 600])

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def add_tree_items(self, tree):
        # Sample structure
        root = QTreeWidgetItem(tree, ["My Software Notes"])
        db_section = QTreeWidgetItem(root, ["MySQL"])
        QTreeWidgetItem(db_section, ["MVCC and Concurrency"])
        QTreeWidgetItem(db_section, ["Transaction Isolation Levels"])
        QTreeWidgetItem(root, ["Java Interview"])
        QTreeWidgetItem(root, ["Python Projects"])
        tree.expandAll()

    def on_tree_item_clicked(self, item, column):
        # Example action when a tree item is clicked
        content = f"Displaying content for: {item.text(column)}"
        self.editor.setText(content)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NotesApp()
    window.show()
    sys.exit(app.exec())
