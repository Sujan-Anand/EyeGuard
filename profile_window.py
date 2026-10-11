"""
The small profile window of the desktop app.

It opens when EyeGuard starts without --profile, and again when you press p
in the video window. Pick a saved profile and press Start, make a new one on
a single form, or continue without a profile.

Only the window is here. Everything it decides (which profile is
pre-selected, whether the form is valid, what counts as a duplicate name)
comes from profiles.py, so that logic is tested without opening a window.
tkinter is part of Python, so nothing extra needs installing.
"""

import profiles

# same colours as the website and the mini window
BACKGROUND, SURFACE, BORDER = "#0B1F21", "#12302F", "#1F4A48"
INK, MUTED, AMBER, ALERT = "#E8F1EF", "#A9C4C0", "#F2A541", "#F26B5B"
WIDTH, HEIGHT = 460, 500
WEAR = [("none", "Nothing"), ("glasses", "Glasses"), ("contacts", "Contact lenses")]


def row_text(profile):
    """One line of the list: name, what they wear, and whether it is calibrated."""
    calibrated = "calibrated" if profiles.is_calibrated(profile) else "not calibrated"
    return f"{profile['name']}  ·  {profiles.describe(profile)}  ·  {calibrated}"


class Window:
    """result is ("use", profile), ("none", None) for "Continue without
    profile", or ("cancel", None) if the window was closed."""

    def __init__(self, current=None, path=None, last_path=None):
        import tkinter as tk
        from tkinter import messagebox
        self.tk, self.messagebox = tk, messagebox
        self.path, self.last_path = path, last_path
        self.result = ("cancel", None)
        self.saved, selected = profiles.picker_choices(path, last_path)
        if current:                                  # reopened with p: show who is in use now
            for index, profile in enumerate(self.saved):
                if profiles.name_key(profile["name"]) == profiles.name_key(current):
                    selected = index

        self.root = root = tk.Tk()
        root.title("EyeGuard")
        root.configure(bg=BACKGROUND)
        root.resizable(False, False)
        x = (root.winfo_screenwidth() - WIDTH) // 2
        y = max(0, (root.winfo_screenheight() - HEIGHT) // 2 - 40)
        root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.attributes("-topmost", True)            # not hidden behind the terminal
        root.after(300, lambda: root.attributes("-topmost", False))

        self.picker = self._build_picker(selected)
        self.form = self._build_form()
        self.show_picker()
        root.lift()
        root.focus_force()

    # ------------------------------------------------------------ small parts
    def _label(self, parent, text, size=12, colour=INK, bold=False, **pack):
        label = self.tk.Label(parent, text=text, bg=parent["bg"], fg=colour, justify="left",
                              anchor="w", wraplength=WIDTH - 48,
                              font=("Segoe UI", -size, "bold" if bold else "normal"))
        label.pack(fill="x", **pack)
        return label

    def _button(self, parent, text, command, primary=False, **options):
        return self.tk.Button(
            parent, text=text, command=command, relief="flat", cursor="hand2",
            bg=AMBER if primary else SURFACE, fg=BACKGROUND if primary else INK,
            activebackground=AMBER, activeforeground=BACKGROUND, disabledforeground=MUTED,
            font=("Segoe UI", -13, "bold"), padx=14, pady=7, **options)

    # ------------------------------------------------------------- the picker
    def _build_picker(self, selected):
        tk = self.tk
        frame = tk.Frame(self.root, bg=BACKGROUND, padx=24, pady=20)
        self._label(frame, "EyeGuard", 20, AMBER, bold=True)
        self._label(frame, "Who is using EyeGuard?", 14, bold=True, pady=(2, 10))
        if self.saved:
            self.listbox = tk.Listbox(
                frame, height=min(8, max(4, len(self.saved))), activestyle="none",
                exportselection=False, bg=SURFACE, fg=INK, selectbackground=AMBER,
                selectforeground=BACKGROUND, highlightthickness=1, highlightbackground=BORDER,
                relief="flat", font=("Segoe UI", -13))
            for profile in self.saved:
                self.listbox.insert("end", "  " + row_text(profile))
            self.listbox.selection_set(selected)
            self.listbox.see(selected)
            self.listbox.pack(fill="x")
            self.listbox.bind("<Double-Button-1>", lambda event: self.start())
            self.listbox.bind("<Return>", lambda event: self.start())
            self._label(frame, "Click a profile, then press Start.", 12, MUTED, pady=(6, 0))
        else:
            self.listbox = None
            self._label(frame, "No profiles yet. A profile tells EyeGuard what you wear at "
                               "the computer, so the distance reading is right for you.",
                        13, MUTED, pady=(0, 6))
        buttons = tk.Frame(frame, bg=BACKGROUND)
        buttons.pack(fill="x", pady=(16, 0))
        self.start_button = self._button(buttons, "Start", self.start, primary=True,
                                         state="normal" if self.saved else "disabled")
        self.start_button.pack(side="left")
        self.new_button = self._button(buttons, "+ New profile", self.show_form,
                                       primary=not self.saved)
        self.new_button.pack(side="left", padx=(10, 0))
        self.skip_link = tk.Label(frame, text="Continue without profile", bg=BACKGROUND,
                                  fg=MUTED, cursor="hand2",
                                  font=("Segoe UI", -13, "underline"))
        self.skip_link.pack(anchor="w", pady=(18, 0))
        self.skip_link.bind("<Button-1>", lambda event: self.skip())
        return frame

    def show_picker(self):
        self.form.pack_forget()
        self.picker.pack(fill="both", expand=True)
        self.root.bind("<Escape>", lambda event: self.close())

    def start(self):
        """Start with the profile selected in the list."""
        if not self.saved:
            return
        chosen = self.listbox.curselection()
        self.use(self.saved[chosen[0] if chosen else 0])

    def use(self, profile):
        profiles.remember_last(profile["name"], self.last_path)
        self.result = ("use", profile)
        self.root.destroy()

    def skip(self):
        self.result = ("none", None)
        self.root.destroy()

    def close(self):
        self.result = ("cancel", None)
        self.root.destroy()

    # --------------------------------------------------------------- the form
    def _build_form(self):
        tk = self.tk
        frame = tk.Frame(self.root, bg=BACKGROUND, padx=24, pady=16)
        self._label(frame, "New profile", 18, AMBER, bold=True, pady=(0, 6))

        self._label(frame, "Name", 13, bold=True)
        self.name = tk.StringVar()
        self.name_entry = tk.Entry(frame, textvariable=self.name, bg=SURFACE, fg=INK,
                                   insertbackground=INK, relief="flat",
                                   highlightthickness=1, highlightbackground=BORDER,
                                   highlightcolor=AMBER, font=("Segoe UI", -14))
        self.name_entry.pack(fill="x", ipady=5, pady=(2, 10))

        self._label(frame, "What do you wear at the computer?", 13, bold=True)
        self.correction = "none"
        row = tk.Frame(frame, bg=BACKGROUND)
        row.pack(fill="x", pady=(4, 8))
        self.wear_buttons = {}
        for column, (value, text) in enumerate(WEAR):
            button = self._button(row, text, lambda v=value: self.set_correction(v))
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0),
                        ipady=6)
            row.columnconfigure(column, weight=1, uniform="wear")
            self.wear_buttons[value] = button

        # lens power: only shown for glasses and contact lenses
        self.power = 0.0
        self.power_box = tk.Frame(frame, bg=BACKGROUND)
        self._label(self.power_box, "Lens power", 13, bold=True)
        stepper = tk.Frame(self.power_box, bg=BACKGROUND)
        stepper.pack(anchor="w", pady=(2, 0))
        self.minus_button = self._button(stepper, "−", lambda: self.step(-1), width=3)
        self.minus_button.pack(side="left")
        self.power_label = tk.Label(stepper, text="0.00", width=8, bg=SURFACE, fg=INK,
                                    font=("Segoe UI", -16, "bold"))
        self.power_label.pack(side="left", padx=6, ipady=6)
        self.plus_button = self._button(stepper, "+", lambda: self.step(1), width=3)
        self.plus_button.pack(side="left")
        tk.Label(stepper, text="dioptres", bg=BACKGROUND, fg=MUTED,
                 font=("Segoe UI", -12)).pack(side="left", padx=8)
        self._label(self.power_box, profiles.POWER_HINT, 12, MUTED, pady=(2, 0))

        self.safe_box = tk.Frame(frame, bg=BACKGROUND)
        self.safe_box.pack(fill="x", pady=(8, 0))
        self._label(self.safe_box, "Safe distance from the screen (cm)", 13, bold=True)
        self.safe = tk.IntVar(value=profiles.DEFAULT_SAFE_DISTANCE_CM)
        tk.Scale(self.safe_box, variable=self.safe, orient="horizontal",
                 from_=profiles.DEFAULT_SAFE_DISTANCE_CM, to=profiles.FORM_MAX_SAFE_DISTANCE_CM,
                 bg=BACKGROUND, fg=INK, troughcolor=SURFACE, activebackground=AMBER,
                 highlightthickness=0, relief="flat", font=("Segoe UI", -12)).pack(fill="x")

        self.message = self._label(frame, "", 12, ALERT, pady=(6, 0))
        buttons = tk.Frame(frame, bg=BACKGROUND)
        buttons.pack(fill="x", side="bottom")
        self.save_button = self._button(buttons, "Save & start", self.save, primary=True)
        self.save_button.pack(side="left")
        self._button(buttons, "Back", self.show_picker).pack(side="left", padx=(10, 0))
        self.name_entry.bind("<Return>", lambda event: self.save())
        self.set_correction("none")
        return frame

    def show_form(self):
        self.picker.pack_forget()
        self.form.pack(fill="both", expand=True)
        self.message.configure(text="")
        self.root.bind("<Escape>", lambda event: self.show_picker())
        self.name_entry.focus_set()

    def set_correction(self, value):
        self.correction = value
        for name, button in self.wear_buttons.items():
            chosen = name == value
            button.configure(bg=AMBER if chosen else SURFACE, fg=BACKGROUND if chosen else INK)
        if profiles.needs_power(value):
            self.power_box.pack(fill="x", before=self.safe_box)
        else:
            self.power_box.pack_forget()

    def power_shown(self):
        return bool(self.power_box.winfo_manager())

    def step(self, steps):
        self.power = profiles.step_power(self.power, steps)
        self.power_label.configure(text=profiles.power_text(self.power))

    def save(self):
        """Save & start: checks the form, then starts with the new profile."""
        result, value = profiles.create_from_form(
            self.name.get(), self.correction, self.power, self.safe.get(),
            self.path, self.last_path)
        if result == "ok":
            self.use(value)
        elif result == "duplicate":
            if self.messagebox.askyesno(
                    "EyeGuard", f'A profile called "{value["name"]}" is already saved '
                                f"({profiles.describe(value)}).\n\nUse that profile?",
                    parent=self.root):
                self.use(value)
            else:
                self.message.configure(text="Choose a different name for the new profile.")
                self.name_entry.focus_set()
        else:
            self.message.configure(text=value)


def choose(current=None, path=None):
    """Opens the window and waits. Returns ("use", profile), ("none", None)
    or ("cancel", None). `current` is the name of the profile in use now."""
    window = Window(current, path)
    window.root.mainloop()
    return window.result
