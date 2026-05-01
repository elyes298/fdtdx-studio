import json

from nicegui import events, ui

from fdtdx_studio.ui.ui_elements.view_helper import ViewHelper


def scale_number(float_rgb):
    int_rgb = []
    for val in float_rgb:
        int_rgb.append(int(255 * val))

    return tuple(int_rgb)
    # return (to_max - to_min) * (unscaled - from_min) / (from_max - from_min) + to_min


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % scale_number(rgb)


class MainSection:
    def __init__(self, controller):
        self.objects = {}
        self.colors = {}
        self.controller = controller
        self.camera_distance_base = (-20, 0, 0)
        self.unit_scale = 1000000  # 1 unit = 1 micrometer

        with ui.element().classes("w-full h-[90vh] flex flex-col top-0"):
            with ui.scene(grid=False, show_stats=False, on_click=self.handle_click).style(
                "position: absolute; top: 0; left: 0; width: 100%; height: 100%;z-index: 1;"
            ) as self.scene:
                pass

            ViewHelper(self.scene)

            ui.button(icon="center_focus_strong", on_click=self.center_view).props("flat").style(
                "position: absolute; bottom: 1%; right: 1%; width: 5%; height: 5%;z-index: 2;"
            ).tooltip("Center Scene")

    def center_view(self):
        x, y, z = self.camera_distance_base
        self.scene.move_camera(x=x, y=y, z=z, look_at_x=0, look_at_y=0, look_at_z=0, duration=0)

    def _coplanar_object_names(self) -> list[str]:
        return [n for n in self.objects if n != "Simulation_Volume"]

    def _apply_coplanar_depth_bias(self) -> None:
        names = self._coplanar_object_names()
        if not names:
            return
        ranked = {name: i + 1 for i, name in enumerate(names)}
        payload = json.dumps(ranked)
        scene_id = int(self.scene.id)
        ui.run_javascript(
            f"""
            const el = getElement({scene_id});
            const vue = el && el.$root && el.$root.$refs && el.$root.$refs['r{scene_id}'];
            if (!vue || !vue.scene) return;
            const rankByName = {payload};
            vue.scene.traverse((obj) => {{
                if (!obj.isMesh || !obj.material || !obj.name) return;
                const rank = rankByName[obj.name];
                if (!rank) return;
                const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                for (const mat of mats) {{
                    if (!mat || mat.isLineBasicMaterial) continue;
                    mat.polygonOffset = true;
                    mat.polygonOffsetFactor = rank;
                    mat.polygonOffsetUnits = rank;
                    mat.needsUpdate = true;
                }}
            }});
            """
        )

    def add_object(self, obj, *, refresh_depth_bias: bool = True):
        name = obj[0]

        with self.scene:
            if isinstance(obj[4], tuple):
                self.colors[name] = rgb_to_hex(obj[4])
                box = (
                    ui.scene.box(obj[2][0] * self.unit_scale, obj[2][1] * self.unit_scale, obj[2][2] * self.unit_scale)
                    .move(obj[3][0] * self.unit_scale, obj[3][1] * self.unit_scale, obj[3][2] * self.unit_scale)
                    .material(self.colors[name])
                )
            else:
                self.colors[name] = obj[4]
                box = (
                    ui.scene.box(obj[2][0] * self.unit_scale, obj[2][1] * self.unit_scale, obj[2][2] * self.unit_scale)
                    .move(obj[3][0] * self.unit_scale, obj[3][1] * self.unit_scale, obj[3][2] * self.unit_scale)
                    .material(self.colors[name])
                )

        self.objects[name] = box.with_name(name)
        if refresh_depth_bias:
            self._apply_coplanar_depth_bias()

    # clear the entire 3d scene and then add all objects in der objectlist
    def update(self, objects):
        self.scene.clear()
        self.objects.clear()
        self.add_simulation_volume(objects[0], refresh_depth_bias=False)
        for obj in objects[1:]:  # remove [1:] if simulation volume should also be drawn
            if obj[1] != "PerfectlyMatchedLayer":
                self.add_object(obj, refresh_depth_bias=False)
        self._apply_coplanar_depth_bias()

    def delete_object(self, name):
        self.objects[name].delete()
        result = self.objects.pop(name)
        self._apply_coplanar_depth_bias()
        return result

    def change_color(self, name, color):
        if isinstance(color, tuple):
            self.colors.update({name: rgb_to_hex(color)})
            self.objects[name].material(self.colors[name])
        else:
            self.colors[name] = color
            self.objects[name].material(color)

    # TODO: depricate?
    def scale_scene_object(self, name, x, y, z):
        if self.objects is not None:
            self.objects[name].scale(x * self.unit_scale, y * self.unit_scale, z * self.unit_scale)
            self._apply_coplanar_depth_bias()

    # TODO: depricate?
    def move_scene_object(self, name, x, y, z):
        self.objects[name].move(x * self.unit_scale, y * self.unit_scale, z * self.unit_scale)
        self._apply_coplanar_depth_bias()

    def highlight(self, name):
        self.downplay()
        for n, obj in self.objects.items():
            if n not in [name, "Simulation_Volume"]:
                obj.material(self.colors[n], opacity=0.4)
        self._apply_coplanar_depth_bias()

    def downplay(self):
        for key, value in self.objects.items():
            if value != self.objects["Simulation_Volume"]:
                value.material(self.colors[key], opacity=1)
        self._apply_coplanar_depth_bias()

    def add_simulation_volume(self, volume, *, refresh_depth_bias: bool = True):
        volume_units = (volume[2][0] * self.unit_scale, volume[2][1] * self.unit_scale, volume[2][2] * self.unit_scale)
        with self.scene:
            box = ui.scene.box(1, 1, 1, wireframe=True).material("#888888")
        box.scale(*volume_units)
        # Adjust camera distance based on max volume size: positioned on negative X looking at origin
        # This keeps X pointing back (into the scene) and Z pointing up. (Y will point Left due to right-handed coordinates)
        max_dim = max(volume_units) if volume_units else 1.0
        MIN_CAMERA_DIM = 1e-3
        max_dim = max(max_dim, MIN_CAMERA_DIM)
        self.camera_distance_base = (-max_dim * 1.5, 0, 0)
        self.center_view()
        self.objects["Simulation_Volume"] = box
        if refresh_depth_bias:
            self._apply_coplanar_depth_bias()

    def handle_click(self, e: events.SceneClickEventArguments):
        name = next((hit.object_name for hit in e.hits if hit.object_name), None)
        if name is not None:
            self.controller.choose_box(name)
