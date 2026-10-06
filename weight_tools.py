bl_info = {
    "name": "Weight Tools - Bone Center Falloff",
    "author": "Weight Tools",
    "version": (1, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Weight Tools",
    "description": "Distribuição de pesos por projeção no osso ativo",
    "category": "Rigging",
}

import bpy
import bmesh

from bpy.props import FloatProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup


def calculate_weight(t, start, end, max_weight, smoothness):
    """
    Peso zero nos limites e fora deles.
    Peso máximo no centro anatômico do osso: t = 0.5.

    Smoothness:
        0 = transição linear;
        1 = smootherstep, com primeira e segunda derivadas nulas
            nos limites e no centro.
    """
    if t <= start or t >= end:
        return 0.0

    if t <= 0.5:
        u = (t - start) / (0.5 - start)
    else:
        u = (end - t) / (end - 0.5)

    u = max(0.0, min(1.0, u))

    # Smootherstep: 6u⁵ - 15u⁴ + 10u³.
    smooth_curve = u * u * u * (u * (6.0 * u - 15.0) + 10.0)

    # Interpolação entre a rampa linear e a curva suavizada.
    falloff = (1.0 - smoothness) * u + smoothness * smooth_curve
    return max(0.0, min(max_weight, max_weight * falloff))


def resolve_target(context):
    """Valida o alvo e transforma o osso para o espaço local da malha."""
    obj = context.active_object

    if obj is None or obj.type != 'MESH':
        raise ValueError("Ative uma malha.")

    if obj.mode not in {'OBJECT', 'EDIT', 'WEIGHT_PAINT'}:
        raise ValueError("Use Object, Edit ou Weight Paint Mode.")

    if obj.mode == 'EDIT' and len(context.objects_in_mode) != 1:
        raise ValueError("Use Edit Mode com apenas uma malha.")

    group = obj.vertex_groups.active

    if group is None:
        raise ValueError("Selecione um grupo de vértices ativo.")

    if group.lock_weight:
        raise ValueError("O grupo de vértices ativo está bloqueado.")

    # Não escolhe silenciosamente um rig quando existem vários.
    rigs = {}
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE' and modifier.object:
            rig = modifier.object
            rigs[rig.as_pointer()] = rig

    if not rigs:
        rig = obj.find_armature()
        if rig is not None:
            rigs[rig.as_pointer()] = rig

    if len(rigs) != 1:
        raise ValueError(
            "A malha deve possuir um único Armature associado."
        )

    rig = next(iter(rigs.values()))
    bone = rig.data.bones.active

    if bone is None:
        raise ValueError("Selecione um osso ativo no Armature.")

    if group.name != bone.name:
        raise ValueError(
            f"O grupo '{group.name}' não corresponde "
            f"ao osso ativo '{bone.name}'."
        )

    if not bone.use_deform:
        raise ValueError("Ative Deform no osso selecionado.")

    try:
        world_to_mesh = obj.matrix_world.inverted()
    except ValueError:
        raise ValueError(
            "A transformação da malha não é invertível. "
            "Verifique se existe escala zero."
        ) from None

    # Armature Object Space -> World Space -> Mesh Object Space.
    rig_to_mesh = world_to_mesh @ rig.matrix_world

    # A malha original está em repouso. Usamos também o osso em
    # repouso, evitando resultados dependentes do quadro da animação.
    head = rig_to_mesh @ bone.head_local
    tail = rig_to_mesh @ bone.tail_local

    direction = tail - head
    length_squared = direction.length_squared

    if length_squared <= 1e-16:
        raise ValueError("O osso tem comprimento nulo ou muito pequeno.")

    return obj, group, head, direction, length_squared


class WEIGHTTOOLS_PG_settings(PropertyGroup):
    """
    Configuração persistente armazenada na Scene.
    Os valores são salvos no .blend e compartilhados pelo painel
    e pelo operador.
    """

    max_weight: FloatProperty(
        name="Max Weight",
        description="Peso máximo no centro do osso",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )

    start_boundary: FloatProperty(
        name="Start Boundary",
        description="Início da influência; deve ser menor que 0.5",
        default=0.0,
        min=0.0,
        max=1.0,
        precision=3,
    )

    end_boundary: FloatProperty(
        name="End Boundary",
        description="Fim da influência; deve ser maior que 0.5",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )

    falloff_smoothness: FloatProperty(
        name="Falloff Smoothness",
        description="0: rampa linear; 1: transição totalmente suavizada",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )


class WEIGHTTOOLS_OT_distribute(Operator):
    bl_idname = "weight_tools.distribute"
    bl_label = "Distribute Selected Weights"
    bl_description = (
        "Distribui pesos apenas nos vértices selecionados "
        "do grupo correspondente ao osso ativo"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and obj.mode in {'OBJECT', 'EDIT', 'WEIGHT_PAINT'}
        )

    def execute(self, context):
        # Sem propriedades internas no operador:
        # lê a configuração atual diretamente da Scene.
        props = context.scene.weight_tools_props

        start = props.start_boundary
        end = props.end_boundary
        intensity = props.max_weight
        smoothness = props.falloff_smoothness

        # O centro anatômico deve estar dentro dos limites.
        # Limites iguais ao centro criariam condições contraditórias:
        # peso máximo e peso zero no mesmo ponto.
        if not (0.0 <= start < 0.5 < end <= 1.0):
            self.report(
                {'ERROR'},
                "Os limites devem satisfazer: Start < 0.5 < End.",
            )
            return {'CANCELLED'}

        try:
            obj, group, head, direction, length_squared = resolve_target(
                context
            )
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        if obj.mode == 'WEIGHT_PAINT':
            if not obj.data.use_paint_mask_vertex:
                self.report(
                    {'ERROR'},
                    "Ative Vertex Selection Masking e selecione os vértices.",
                )
                return {'CANCELLED'}

        edit_mode = obj.mode == 'EDIT'
        owns_bmesh = not edit_mode
        bm = None

        try:
            if edit_mode:
                # Este BMesh pertence ao Blender.
                bm = bmesh.from_edit_mesh(obj.data)
            else:
                # Cópia temporária somente para seleção e cálculo.
                bm = bmesh.new()
                bm.from_mesh(obj.data)

            bm.verts.ensure_lookup_table()
            bm.verts.index_update()

            updates = []

            for vertex in bm.verts:
                # Nenhum cálculo ou escrita de peso em vértices
                # não selecionados ou ocultos.
                if not vertex.select or vertex.hide:
                    continue

                # Projeção vetorial normalizada:
                #
                # d = tail - head
                # t = dot(vertex - head, d) / dot(d, d)
                #
                # dot(d, d) = comprimento² do osso.
                # Head -> t = 0
                # Centro -> t = 0.5
                # Tail -> t = 1
                #
                # vertex.co, head e tail estão no mesmo Object Space.
                t = (vertex.co - head).dot(direction) / length_squared
                t = max(0.0, min(1.0, t))

                weight = calculate_weight(
                    t,
                    start,
                    end,
                    intensity,
                    smoothness,
                )
                updates.append((vertex, weight))

            if not updates:
                self.report({'WARNING'}, "Nenhum vértice selecionado.")
                return {'CANCELLED'}

            if edit_mode:
                # Altera somente a entrada do grupo ativo na camada
                # de deformação dos vértices selecionados.
                layer = bm.verts.layers.deform.verify()

                for vertex, weight in updates:
                    deform = vertex[layer]

                    if weight > 0.0:
                        deform[group.index] = weight
                    elif group.index in deform:
                        del deform[group.index]

                bmesh.update_edit_mesh(
                    obj.data,
                    loop_triangles=False,
                    destructive=False,
                )

            else:
                # VertexGroup.add não funciona em Edit Mode, mas
                # permite escrita pontual em Object/Weight Paint.
                #
                # Não usamos bm.to_mesh(): assim não regravamos
                # geometria, UVs ou shape keys desnecessariamente.
                for vertex, weight in updates:
                    if weight > 0.0:
                        group.add([vertex.index], weight, 'REPLACE')
                    else:
                        group.remove([vertex.index])

                obj.data.update()

            count = len(updates)

        finally:
            if owns_bmesh and bm is not None:
                bm.free()

        # Não executamos normalização automática: ela modificaria
        # os pesos de outros grupos, contrariando o isolamento.
        obj.update_tag()

        if context.screen:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

        self.report(
            {'INFO'},
            f"{count} vértices atualizados no grupo '{group.name}'.",
        )
        return {'FINISHED'}


class WEIGHTTOOLS_PT_panel(Panel):
    bl_idname = "WEIGHTTOOLS_PT_panel"
    bl_label = "Weight Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Weight Tools"

    def draw(self, context):
        layout = self.layout
        props = context.scene.weight_tools_props
        obj = context.active_object

        # Painel fixo na Sidebar (N), com controles vinculados
        # diretamente ao PropertyGroup persistente.
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.prop(props, "max_weight", slider=True)
        layout.prop(props, "start_boundary", slider=True)
        layout.prop(props, "end_boundary", slider=True)
        layout.prop(props, "falloff_smoothness", slider=True)

        valid_bounds = (
            props.start_boundary < 0.5 < props.end_boundary
        )

        if not valid_bounds:
            warning = layout.column()
            warning.alert = True
            warning.label(text="Start < 0.5 < End", icon='ERROR')

        layout.separator()

        if obj and obj.type == 'MESH':
            group = obj.vertex_groups.active
            layout.label(
                text=f"Group: {group.name if group else 'None'}"
            )

            if obj.mode == 'WEIGHT_PAINT':
                layout.prop(
                    obj.data,
                    "use_paint_mask_vertex",
                    text="Vertex Selection Mask",
                )

        layout.label(text="Somente vértices selecionados.")
        layout.label(text="Pico no centro do osso: 0.5.")

        row = layout.row()
        row.scale_y = 1.8
        row.enabled = valid_bounds
        row.operator(WEIGHTTOOLS_OT_distribute.bl_idname)


def draw_weights_menu(self, context):
    self.layout.separator()
    self.layout.operator(
        WEIGHTTOOLS_OT_distribute.bl_idname,
        text="Bone Center Falloff — Selected",
    )


CLASSES = (
    WEIGHTTOOLS_PG_settings,
    WEIGHTTOOLS_OT_distribute,
    WEIGHTTOOLS_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.weight_tools_props = PointerProperty(
        type=WEIGHTTOOLS_PG_settings
    )

    # Acesso adicional pelo menu Weights do Weight Paint.
    bpy.types.VIEW3D_MT_paint_weight.append(draw_weights_menu)


def unregister():
    bpy.types.VIEW3D_MT_paint_weight.remove(draw_weights_menu)

    del bpy.types.Scene.weight_tools_props

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()