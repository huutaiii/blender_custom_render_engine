"""
Simple Render Engine
++++++++++++++++++++
"""

import bpy
import array
import gpu
from gpu_extras.presets import draw_texture_2d
import bgl
from gpu_extras.batch import batch_for_shader
import numpy as np
from random import random
import time
import mathutils
import bl_math

VERTEX_SHADER = open("VertexShader.glsl").read()
GEOMETRY_SHADER = open("GeometryShader.glsl").read()
PIXEL_SHADER = open("PixelShader.glsl").read()

class CustomRenderEngine(bpy.types.RenderEngine):
    # These three members are used by blender to set up the
    # RenderEngine; define its internal name, visible name and capabilities.
    bl_idname = "CUSTOM"
    bl_label = "Custom"
    bl_use_preview = True

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        self.draw_calls = {}
        self.lights = []
        self.mesh_objects = []

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        scene = depsgraph.scene
        scale = scene.render.resolution_percentage / 100.0
        self.size_x = int(scene.render.resolution_x * scale)
        self.size_y = int(scene.render.resolution_y * scale)

        # Fill the render result with a flat color. The framebuffer is
        # defined as a list of pixels, each pixel itself being a list of
        # R,G,B,A values.
        if self.is_preview:
            color = [0.1, 0.2, 0.1, 1.0]
        else:
            color = [0.2, 0.1, 0.1, 1.0]

        pixel_count = self.size_x * self.size_y
        rect = [color] * pixel_count

        # Here we write the pixel values to the RenderResult
        result = self.begin_result(0, 0, self.size_x, self.size_y)
        layer = result.layers[0].passes["Combined"]
        layer.rect = rect
        self.end_result(result)

    # For viewport renders, this method gets called once at the start and
    # whenever the scene or 3D viewport changes. This method is where data
    # should be read from Blender in the same thread. Typically a render
    # thread will be started to do the work while keeping Blender responsive.
    def view_update(self, context, depsgraph):
        region = context.region
        view3d = context.space_data
        scene = depsgraph.scene

        # Get viewport dimensions
        dimensions = region.width, region.height
        
        if not self.scene_data:
            # First time initialization
            print("AAAAAAAAAAAAAAAAAAAAAAAAAAaaa", flush=True)
            self.scene_data = [0]
            first_time = True

            # Loop over all datablocks used in the scene.
            for datablock in depsgraph.ids:
                if isinstance(datablock, bpy.types.Object) and datablock.type == 'MESH':
                    print(datablock.type, " ", datablock.name, flush=True)
                    draw = MeshDraw(datablock.data)
                    draw.object = datablock
                    self.draw_calls[datablock.name] = draw
                pass
        else:
            first_time = False

            # Test which datablocks changed
            for update in depsgraph.updates:
                # print("Datablock updated: ", update.id.name, flush=True)
                datablock = update.id
                if isinstance(datablock, bpy.types.Object) \
                and datablock.type == 'MESH' and update.is_updated_geometry:
                    print("mesh updated: ", datablock.name, flush=True)
                    # del self.draw_calls[datablock.name]
                    draw = MeshDraw(datablock.data)
                    draw.object = datablock
                    self.draw_calls[datablock.name] = draw

            # Test if any material was added, removed or changed.
            if depsgraph.id_type_updated('MATERIAL'):
                # print("Materials updated")
                pass

        # Loop over all object instances in the scene.
        if first_time or depsgraph.id_type_updated('OBJECT'):
            pass
            self.mesh_objects = []
            for instance in depsgraph.object_instances:
                object = instance.object
                if object.type == 'MESH':
                    self.mesh_objects.append(object)
            self.lights = []
            # for light in self.lights:
            #     self.lights.remove(light)
            for instance in depsgraph.object_instances:
                object = instance.object
                if object.type == 'LIGHT':
                    if object.data.type == 'SUN':
                        # print("light: ", object.name)
                        light_direction = mathutils.Vector((0, 0, 1))
                        light_direction.rotate(object.matrix_world.decompose()[1])
                        self.lights.append(light_direction)

            
    # For viewport renders, this method is called whenever Blender redraws
    # the 3D viewport. The renderer is expected to quickly draw the render
    # with OpenGL, and not perform other expensive work.
    # Blender will draw overlays for selection and editing on top of the
    # rendered image automatically.
    def view_draw(self, context, depsgraph):
        region = context.region
        scene = depsgraph.scene

        # Get viewport dimensions
        dimensions = region.width, region.height

        # bgl.glClearColor(1, 0, 0, 1)
        # bgl.glClear(bgl.GL_COLOR_BUFFER_BIT | bgl.GL_DEPTH_BUFFER_BIT | bgl.GL_STENCIL_BUFFER_BIT)

        # Bind (fragment) shader that converts from scene linear to display space,
        # self.bind_display_space_shader(scene)
        # gpu.state.blend_set('ALPHA')
        gpu.state.depth_mask_set(True)
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.face_culling_set('BACK')

        settings = context.scene.custom_render_engine
        for object in self.mesh_objects:
            draw = self.draw_calls[object.name]
            draw.draw(object.matrix_world, context.region_data, self.lights, settings)
        # for key, draw in self.draw_calls.items():
        #     print(draw.object.name, " ", draw.object.hide_viewport, flush=True)
        #     draw.draw(draw.object.matrix_world, context.region_data, self.lights, settings)
            

        # self.unbind_display_space_shader()
        # gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)
        gpu.state.face_culling_set('NONE')

class MeshDraw:
    def __init__(self, mesh, transform=None):
        # print("AAAAAAAAAAAAAAA", mesh, flush=True)
        self.transform = transform
        mesh.calc_loop_triangles()
        use_split_normals = True
        try:
            mesh.calc_tangents()
        except RuntimeError:
            use_split_normals = False

        vertices = np.empty((len(mesh.loops), 3), dtype=np.float32)
        color = np.zeros((len(mesh.loops), 4), dtype=np.float32)
        normals = np.empty((len(mesh.loops), 3), dtype=np.float32)
        indices = np.empty((len(mesh.loop_triangles), 3), dtype=np.uintc)
        
        merged_vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        mesh.vertices.foreach_get("co", np.reshape(merged_vertices, len(mesh.vertices) * 3))
        loop_vertices = np.empty(len(mesh.loops), dtype=np.int)
        mesh.loops.foreach_get("vertex_index", loop_vertices)
        start_time = time.time()
        # this is not fast enough ?
        for i in range(len(mesh.loops)):
            vertices[i] = merged_vertices[loop_vertices[i]]
        # print(time.time() - start_time)
        mesh.loop_triangles.foreach_get("loops", np.reshape(indices, len(mesh.loop_triangles) * 3))
        mesh.loops.foreach_get("normal", np.reshape(normals, len(mesh.loops) * 3))
        if mesh.vertex_colors.active:
            mesh.vertex_colors.active.data.foreach_get("color", np.reshape(color, len(mesh.loops) * 4))

        # fmt = gpu.types.GPUVertFormat()
        # fmt.attr_add(id="position", comp_type='F32', len=3, fetch_mode="FLOAT")
        # fmt.attr_add(id="color", comp_type='F32', len=4, fetch_mode="FLOAT")

        # vbo = gpu.types.GPUVertBuf(len=len(vertices), format=fmt)
        # vbo.attr_fill(id="position", data=vertices)
        # vbo.attr_fill(id="color", data=color)

        # ibo = gpu.types.GPUIndexBuf(types="TRIS", seq=indices)

        self.shader = gpu.types.GPUShader(VERTEX_SHADER, PIXEL_SHADER, geocode=GEOMETRY_SHADER)
        self.batch = batch_for_shader(self.shader, 'TRIS', {"position": vertices, "normal": normals, "color": color}, indices=indices)
    
    def draw(self, transform, region_data, lights, settings):
        def min(a, b):
            if a > b:
                return b
            else:
                return a

        self.shader.bind()
        try:
            self.shader.uniform_float("matrix_world", transform)
            # self.shader.uniform_float("perspective_matrix", perspective_matrix)
            self.shader.uniform_float("view_matrix", region_data.view_matrix)
            self.shader.uniform_float("projection_matrix", region_data.window_matrix)
            packed_lights = mathutils.Matrix.Diagonal(mathutils.Vector((0, 0, 0, 0)))
            for i in range(min(len(lights), 4)):
                packed_lights[i].xyz = lights[i]
            self.shader.uniform_float("directional_lights", packed_lights.transposed())
            self.shader.uniform_bool("render_outlines", [settings.enable_outline])
            self.shader.uniform_float("outline_width", settings.outline_width)
            self.shader.uniform_float("shading_sharpness", settings.shading_sharpness)
        except ValueError:
            pass
        self.batch.draw(self.shader)

class CustomRenderEngineSettings(bpy.types.PropertyGroup):
    enable_outline: bpy.props.BoolProperty(name="Render Outlines", default=True)
    outline_width: bpy.props.FloatProperty(name="Outline Width", default=1, min=0, soft_max=100)
    shading_sharpness: bpy.props.FloatProperty(name="Shading Sharpness", default=1, subtype='FACTOR', min=0, max=1)

class CustomRenderEnginePanel(bpy.types.Panel):
    bl_idname = "RENDER_PT_CustomRenderEngine"
    bl_label = "AAAAAAAAAAAaaaaaaaaaaaa"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    # COMPAT_ENGINES = {'CUSTOM'}

    @classmethod
    def poll(cls, context):
        return context.engine == "CUSTOM"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.custom_render_engine
        layout.prop(settings, "enable_outline")
        layout.prop(settings, "outline_width")
        layout.prop(settings, "shading_sharpness")

# RenderEngines also need to tell UI Panels that they are compatible with.
# We recommend to enable all panels marked as BLENDER_RENDER, and then
# exclude any panels that are replaced by custom panels registered by the
# render engine, or that are not supported.
def get_panels():
    exclude_panels = {
        'VIEWLAYER_PT_filter',
        'VIEWLAYER_PT_layer_passes',
    }

    panels = []
    for panel in bpy.types.Panel.__subclasses__():
        if hasattr(panel, 'COMPAT_ENGINES') and 'BLENDER_RENDER' in panel.COMPAT_ENGINES:
            if panel.__name__ not in exclude_panels:
                panels.append(panel)

    return panels

classes = [
    CustomRenderEngine,
    CustomRenderEngineSettings,
    CustomRenderEnginePanel
]

def register():
    # Register the RenderEngine
    for cls in classes:
        bpy.utils.register_class(cls)

    for panel in get_panels():
        panel.COMPAT_ENGINES.add('CUSTOM')

    bpy.types.Scene.custom_render_engine = bpy.props.PointerProperty(type=CustomRenderEngineSettings)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    for panel in get_panels():
        if 'CUSTOM' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('CUSTOM')


if __name__ == "__main__":
    register()
