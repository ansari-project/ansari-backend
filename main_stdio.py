from hermetic.presenters.stdio_presenter import StdioPresenter
from agents.ansari import Ansari

aa = Ansari()
sp = StdioPresenter()

sp.present(aa)