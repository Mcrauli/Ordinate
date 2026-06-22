import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from scan2bim.schemas.model import StructuralModel
from scan2bim.gui.theme import apply_theme
from scan2bim.gui.plan_view import PlanView

app = QtWidgets.QApplication([])
apply_theme(app)
data = json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_merged\floor_00\model.json").read_text())
model = StructuralModel.model_validate(data)
pv = PlanView()
pv.resize(900, 900)
pv.show_model(model)
pv.show()
app.processEvents()
QtCore.QThread.msleep(300)
app.processEvents()
pix = pv.grab()
out = r"C:\Users\lauri\scan2bim\data\output\_gui_plan.png"
pix.save(out)
print("saved", out, pix.width(), pix.height())
