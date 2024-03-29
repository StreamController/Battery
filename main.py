from ast import mod
import json
from math import floor
import re
import threading
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import gtk modules
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Pango

GLib.set_application_name("StreamController")

import sys
import os
from PIL import Image
from loguru import logger as log
import requests
import time
import subprocess
import dbus

# Add plugin to sys.paths
sys.path.append(os.path.dirname(__file__))

# Import globals
import globals as gl

# Import own modules
from src.backend.DeckManagement.DeckController import DeckController
from src.backend.PageManagement.Page import Page

from plugins.com_core447_Battery.ComboRow import ComboRow

class BatteryPercentage(ActionBase):
    def __init__(self, action_id: str, action_name: str,
                 deck_controller: "DeckController", page: Page, coords: str, plugin_base: PluginBase):
        super().__init__(action_id=action_id, action_name=action_name,
            deck_controller=deck_controller, page=page, coords=coords, plugin_base=plugin_base)
        
    def on_ready(self):
        self.on_tick()

    def get_devices(self, fix_charging_duplicates: bool = True) -> dict:
        bus = dbus.SystemBus()
        upower = bus.get_object('org.freedesktop.UPower', '/org/freedesktop/UPower')
        iface = dbus.Interface(upower, 'org.freedesktop.UPower')

        devices = {}
        device_counters = {}
        
        for device_path in iface.EnumerateDevices():
            device = bus.get_object('org.freedesktop.UPower', device_path)
            device_properties = dbus.Interface(device, dbus.PROPERTIES_IFACE)
            
            percentage = float(device_properties.Get('org.freedesktop.UPower.Device', 'Percentage'))
            is_charging = device_properties.Get('org.freedesktop.UPower.Device', 'State') == 1
            # charging_status = "Charging" if is_charging else "Not Charging"
            # device_name = device_properties.Get('org.freedesktop.UPower.Device', 'NativePath')
            model_name = str(device_properties.Get('org.freedesktop.UPower.Device', 'Model'))
            
            if fix_charging_duplicates:
                if model_name in devices:
                    devices[model_name]["percentage"] = max(devices[model_name]["percentage"], percentage)
                    devices[model_name]["is_charging"] = devices[model_name]["is_charging"] or is_charging
                else:
                    devices[model_name] = {
                        "percentage": percentage,
                        "is_charging": is_charging
                    }
            else:
                if model_name in device_counters:
                    device_counters[model_name] += 1
                else:
                    device_counters[model_name] = 1
                    
                new_model_name = f"{model_name}_{device_counters[model_name]}"
                devices[new_model_name] = {
                    "percentage": percentage,
                    "is_charging": is_charging
                }

        return devices
    
    def get_config_rows(self) -> list:
        self.device_model = Gtk.ListStore.new([str])
        # self.device_row = Adw.ComboRow(model=self.device_model, title=self.plugin_base.lm.get("actions.battery-percentage.device-drop-down.title"))
        self.device_row = ComboRow(model=self.device_model, title=self.plugin_base.lm.get("actions.battery-percentage.device-drop-down.title"))

        self.device_renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ellipsize_set=True)
        self.device_row.combo_box.pack_start(self.device_renderer, True)
        self.device_row.combo_box.add_attribute(self.device_renderer, "text", 0)

        self.update_device_model()
        self.load_defaults()

        self.device_row.combo_box.connect("changed", self.on_device_changed)
        return [self.device_row]

    
    def load_defaults(self):
        self.load_selected_device()

    def load_selected_device(self):
        settings = self.get_settings()
        for i, row in enumerate(self.device_model):
            if row[0] == settings.get("device"):
                self.device_row.combo_box.set_active(i)
                return

        self.device_row.combo_box.set_active(-1)

    def on_device_changed(self, combo, *args):
        selected = self.device_model[combo.get_active()][0]

        settings = self.get_settings()
        settings["device"] = selected
        self.set_settings(settings)

    def update_device_model(self):
        # Clear
        self.device_model.clear()

        ## Add
        devices = self.get_devices(fix_charging_duplicates=True)
        for model_name in devices:
            self.device_model.append([model_name])

    def on_tick(self):
        device_name = self.get_settings().get("device", None)
        device = self.get_devices().get(device_name, {})
        percentage = round(device.get("percentage", -1))
        is_charging = device.get("is_charging", False)

        icon_name = self.get_battery_icon_name(percentage, is_charging)
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "battery", icon_name)

        self.set_media(media_path=icon_path, size=0.5, valign=-0.5)
        if percentage < 0:
            percentage = "?"
        else:
            if percentage <= 25:
                self.set_background_color([255, 0, 0, 255])
            elif percentage >= 90:
                self.set_background_color([85, 185, 17, 255])
            else:
                self.set_background_color([0, 0, 0, 0])

        self.set_bottom_label(f"{percentage}%")



    def get_battery_icon_name(self, percent: float, is_charging: bool) -> str:
        if percent < 0:
            return "unknown.png"
        
        charging = "_charging" if is_charging else ""
        icon_index = min(floor(percent // (100 / 8)), 7)  # Ensure the maximum index is 7
        return f"{icon_index}{charging}.png"


class BatteryPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        self.init_locale_manager()

        self.lm = self.locale_manager

        ## Register actions
        self.find_phone_holder = ActionHolder(
            plugin_base=self,
            action_base=BatteryPercentage,
            action_id="com_core447_Battery::BatteryPercentage",
            action_name=self.lm.get("actions.battery-percentage.name"),
        )
        self.add_action_holder(self.find_phone_holder)

        # Register plugin
        self.register(
            plugin_name=self.lm.get("plugin.name"),
            github_repo="https://github.com/StreamController/Counter",
            plugin_version="1.0.0",
            app_version="1.0.0-alpha"
        )

    def init_locale_manager(self):
        self.lm = self.locale_manager
        self.lm.set_to_os_default()