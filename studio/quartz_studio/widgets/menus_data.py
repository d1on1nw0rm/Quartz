from __future__ import annotations


SEP = ("sep",)


def item(text: str, shortcut: str | None = None, icon: str | None = None,
         enabled: bool = True, **flags) -> tuple:
    if flags:
        return ("item", text, shortcut, icon, enabled, flags)
    return ("item", text, shortcut, icon, enabled)


def sub(text: str, entries: list, icon: str | None = None, enabled: bool = True,
        **flags) -> tuple:
    if flags:
        return ("submenu", text, entries, icon, enabled, flags)
    return ("submenu", text, entries, icon, enabled)


def section(title: str) -> tuple:
    return ("section", title)


def _plain(names: list[str | None], icon: str | None = None) -> list:
    return [SEP if n is None else item(n, None, icon) for n in names]



def export_label(fmt) -> str:
    return f"{fmt.label}..."


def _export_items() -> list:
    from quartz_studio import fileio

    return [item(export_label(f)) for f in fileio.exporters()]


FILE_MENU = [
    item("New Project", "Ctrl+N", "file_new"),
    item("Open Project...", "Ctrl+O", "file_open"),
    sub("Open Recent", [
        item("Clear Recent File List"),
    ]),
    item("Merge Project...", "Ctrl+Shift+O"),
    item("Revert to Saved..."),
    SEP,
    item("Close Project", "Ctrl+F4"),
    item("Close All Projects"),
    SEP,
    item("Save Project", "Ctrl+S", "file_save"),
    item("Save Project As...", "Ctrl+Shift+S"),
    item("Save Incremental", "Ctrl+Alt+S"),
    item("Save All Projects"),
    item("Save Project with Assets..."),
    item("Save as Default Scene"),
    SEP,
    item("Import..."),
    sub("Export", [
        *_export_items(),
        SEP,
        item("Export Selection..."),
    ]),
    SEP,
    item("Project Info..."),
    SEP,
    item("Exit", "Alt+F4"),
]


EDIT_MENU = [
    item("Undo", "Ctrl+Z", "undo", False),
    item("Redo", "Ctrl+Y", "redo", False),
    item("Undo History..."),
    SEP,
    item("Cut", "Ctrl+X", None, False),
    item("Copy", "Ctrl+C", None, False),
    item("Paste", "Ctrl+V"),
    item("Delete", "Del", None, False),
    SEP,
    item("Select All", "Ctrl+A"),
    item("Deselect All", "Ctrl+Shift+A"),
    item("Select Children"),
    SEP,
    item("Project Settings...", "Ctrl+D"),
    item("Project Scale..."),
    SEP,
    item("Controls...", "Shift+F12"),
    item("Preferences...", "Ctrl+E", "gear"),
]


_SPLINES = [
    item("Line", None, "m_line"),
    SEP,
    item("Rectangle", None, "rectangle"),
    item("Text Spline", None, "text_spline"),
    item("Profile", None, "profile"),
    item("4-Side", None, "four_side"),
    item("n-Side", None, "n_side"),
    item("Star", None, "star"),
    item("Cogwheel", None, "cogwheel"),
    SEP,
    item("Circle", None, "circle"),
    item("Arc", None, "arc"),
    item("Cissoid", None, "cissoid"),
    item("Cycloid", None, "cycloid"),
    item("Formula", None, "formula"),
    item("Helix", None, "helix"),
    item("Flower", None, "flower"),
]

_MESHES = [
    item("Cube", None, "cube"),
    item("Empty Polygon", None, "empty_polygon"),
    item("Polygon", None, "primitive"),
    item("Plane", None, "plane"),
    item("Bezier", None, "bezier"),
    item("Landscape", None, "landscape"),
    item("Pyramid", None, "pyramid"),
    SEP,
    item("Sphere", None, "sphere"),
    item("Disc", None, "disc"),
    item("Torus", None, "torus"),
    item("Cone", None, "cone"),
    item("Tube", None, "tube"),
    item("Cylinder", None, "cylinder"),
    item("Oil Tank", None, "oil_tank"),
    item("Capsule", None, "capsule"),
    SEP,
    item("Text", None, "text"),
    item("Figure", None, "figure"),
    item("Platonic", None, "platonic"),
]

_GENERATORS = [
    item("Subdivision Surface", None, "subdivision_surface"),
    item("Boole", None, "boolean"),
    item("Symmetry", None, "symmetry_generator"),
    item("Remesh", None, "remesh"),
    item("Connect", None, "connect"),
    item("Cloner", None, "cloner"),
    item("Thicken", None, "thicken"),
    SEP,
    item("Extrude", None, "extrude"),
    item("Sweep", None, "sweep"),
    item("Lathe", None, "lathe"),
    item("Loft", None, "loft"),
    item("Spline Mask", None, "generator"),
    item("Trunk", None, "trunk"),
    item("Vectorizer", None, "generator"),
    item("Relief", None, "generator"),
    SEP,
    item("Volume Builder", None, "volume_builder"),
    item("Volume Mesher", None, "volume_mesher"),
    SEP,
    item("Voronoi Fracture", None, "voronoi"),
    item("Fracture", None, "fracture"),
    item("Cloth Surface", None, "generator"),
    item("Metaball", None, "metaball"),
    item("Array", None, "array"),
]

_DEFORMERS = [
    item("Bend", None, "bend"),
    item("Bulge", None, "deformer"),
    item("Shear", None, "deformer"),
    item("Taper", None, "deformer"),
    item("Twist", None, "twist"),
    item("FFD", None, "ffd"),
    SEP,
    item("Camera", None, "deformer"),
    item("Correction", None, "deformer"),
    item("Mesh", None, "deformer"),
    SEP,
    item("Explosion", None, "deformer"),
    item("Explosion FX", None, "deformer"),
    item("Melt", None, "deformer"),
    item("Shatter", None, "deformer"),
    item("Swing", None, "deformer"),
    item("Squash and Stretch", None, "deformer"),
    item("Collision", None, "deformer"),
    SEP,
    item("Shrink Wrap", None, "deformer"),
    item("Spherify", None, "deformer"),
    item("Delta Mush", None, "deformer"),
    item("Smoothing", None, "deformer"),
    item("Surface", None, "deformer"),
    item("Wrap", None, "deformer"),
    item("Projection", None, "deformer"),
    SEP,
    item("Spline", None, "deformer"),
    item("Spline Rail", None, "deformer"),
    item("Spline Wrap", None, "deformer"),
    SEP,
    item("Displacer", None, "deformer"),
    item("Formula", None, "deformer"),
    item("Wind", None, "deformer"),
    item("Bevel", None, "deformer"),
    item("Python", None, "deformer"),
]

_FIELDS = [
    item("Linear Field", None, "linear_field"),
    item("Radial Field", None, "radial_field"),
    item("Spherical Field", None, "spherical_field"),
    item("Box Field", None, "box_field"),
    item("Cylinder Field", None, "field"),
    item("Cone Field", None, "field"),
    item("Capsule Field", None, "field"),
    item("Torus Field", None, "field"),
    SEP,
    item("Random Field", None, "random_field"),
    item("Shader Field", None, "field"),
    item("Sound Field", None, "field"),
    item("Formula Field", None, "field"),
    item("Python Field", None, "field"),
    SEP,
    item("Group Field", None, "field"),
]

_ENVIRONMENT = [
    item("Physical Sky", None, "sky"),
    item("Sky", None, "sky"),
    item("Floor", None, "floor"),
    item("Environment", None, "environment"),
    item("Background", None, "environment"),
    item("Foreground", None, "environment"),
    item("Stage", None, "environment"),
]

_CAMERAS = [
    item("Camera", None, "camera"),
    item("Target Camera", None, "camera"),
    item("Stereo Camera", None, "camera"),
    SEP,
    item("Motion Camera", None, "camera"),
    item("Camera Morph", None, "camera"),
    item("Camera Crane", None, "camera"),
]

_LIGHTS = [
    item("Light", None, "light"),
    item("Point Light", None, "light"),
    item("Target Light", None, "light"),
    item("Area Light", None, "light"),
    item("PBR Light", None, "light"),
    item("IES Light...", None, "light"),
    item("Infinite Light", None, "light"),
    item("Sun Light", None, "light"),
]

_MATERIALS = [
    item("Standard Material", None, "material"),
    item("PBR Material", None, "material"),
    item("Node Material", None, "material"),
    item("Uber Material", None, "material"),
    SEP,
    item("Hair Material", None, "material"),
    item("Sketch Material", None, "material"),
]

_XREFS = [
    item("XRef", None, "m_xref"),
    item("Simple XRef", None, "m_xref"),
    SEP,
    item("Convert Selection to XRef..."),
    item("Open XRef Project"),
]

_TAGS = [
    item("Material Tag", None, "tag"),
    item("Phong Tag", None, "tag"),
    item("Protection Tag", None, "tag"),
    item("Display Tag", None, "tag"),
    item("Compositing Tag", None, "tag"),
    SEP,
    item("Target Tag", None, "tag"),
    item("Vibrate Tag", None, "tag"),
    item("Align to Spline Tag", None, "tag"),
    item("Python Tag", None, "python"),
]

CREATE_MENU = [
    item("Null", None, "null"),
    section("PRIMITIVES"),
    sub("Spline", _SPLINES),
    sub("Mesh", _MESHES),
    section("OPERATORS"),
    sub("Generator", _GENERATORS),
    sub("Deformer", _DEFORMERS, highlight=True),
    sub("Field", _FIELDS),
    section("VIRTUAL SET"),
    sub("Environment", _ENVIRONMENT),
    sub("Camera", _CAMERAS),
    sub("Light", _LIGHTS),
    section("EXTRA"),
    sub("Material", _MATERIALS),
    sub("XRef", _XREFS),
    sub("Tag", _TAGS, highlight=True),
    section("BAKE"),
    item("Bake as Alembic", None, "m_bake_alembic", False, gear=True),
    item("Bake as Alembic + Delete", None, "m_bake_alembic", False, gear=True),
    SEP,
    item("RS BakeSet", None, "m_bake_set"),
    item("RS Proxy", None, "m_proxy"),
]


MODES_MENU = [
    sub("Execution", [
        item("Animation", None, "m_mode_animation"),
        item("Edit"),
        item("Game Mode"),
    ]),
    sub("Coordinates", [
        item("Object Coordinate System"),
        item("World Coordinate System"),
        SEP,
        item("X-Axis / Pitch", None, "axis_x"),
        item("Y-Axis / Heading", None, "axis_y"),
        item("Z-Axis / Bank", None, "axis_z"),
    ]),
    section("COMPONENTS"),
    item("Points", None, "mode_points"),
    item("Edges", None, "mode_edges"),
    item("Polygons", None, "mode_polygons"),
    section("OBJECTS"),
    item("Model", None, "mode_model", checked=True),
    item("Object", None, "m_mode_object"),
    item("Animation", None, "m_mode_animation"),
    item("Texture", None, "m_mode_texture"),
    section("ADDITIONAL"),
    item("Enable Axis", "L", "axis_enable", gear=True),
    item("UV Mode", None, "m_mode_uv", False),
    section("MODELING"),
    item("Snap", None, "m_snap", checked=True),
    sub("Alignment", [
        item("Align to View"),
        item("Align to Object"),
        item("Align to Selection"),
        SEP,
        item("Locked Workplane"),
    ]),
    item("Modeling Settings", "Shift+M", "m_modeling_settings"),
    item("Workplane", None, "m_workplane"),
    sub("Workplane", [
        item("Align Workplane to X"),
        item("Align Workplane to Y"),
        item("Align Workplane to Z"),
        item("Align Workplane to Selection"),
        SEP,
        item("Reset Workplane"),
    ]),
    item("Enable Symmetry", "Alt+W", "symmetry", gear=True),
    item("Symmetry", None, "m_symmetry_settings"),
    item("Normal Edit", None, "m_normal_edit"),
    section("VIEWPORT SOLO"),
    item("Viewport Solo", None, "m_solo"),
    item("Viewport Solo Hierarchy", None, "m_solo_hierarchy"),
    item("Auto Viewport Solo", None, "m_solo_auto"),
]


SELECT_MENU = [
    section("SELECTION TOOLS"),
    item("Brush Selection", "9", "live_selection"),
    item("Rectangle Selection", "0", "select_rect"),
    item("Lasso Selection", "8", "select_lasso"),
    item("Polygon Selection", None, "select_polygon"),
    sub("Selection Filter", [
        item("Select None"),
        item("Select All"),
        SEP,
        item("Null", None, "null"),
        item("Polygon", None, "primitive"),
        item("Spline", None, "spline"),
        item("Generator", None, "generator"),
        item("Deformer", None, "deformer"),
        item("Camera", None, "camera"),
        item("Light", None, "light"),
    ]),
    section("TOPOLOGICAL SELECTION"),
    item("Loop Selection", "U~L", "select_loop"),
    item("Ring Selection", "U~B"),
    item("Pattern Selection"),
    item("Path Selection", "U~M"),
    item("Phong Angle Selection"),
    item("Stamp Selection"),
    item("Outline Selection", "U~Q"),
    item("Fill Selection", "U~F"),
    section("SELECTION COMMANDS"),
    item("Select All"),
    item("Deselect All"),
    item("Invert", "U~I"),
    item("Select Connected", "U~W"),
    item("Grow Selection", "U~G"),
    item("Shrink Selection", "U~K"),
    SEP,
    item("Hide Selected"),
    item("Hide Unselected"),
    item("Show All"),
    item("Invert Visibility"),
    SEP,
    item("Convert Selection Mode...", "U~X"),
    item("Set Selection"),
    item("Set Vertex Weight..."),
]


TOOLS_MENU = [
    item("Commander...", "Shift+C", "search"),
    section("TRANSFORM TOOLS"),
    item("Move", "E", "move", checked=True),
    item("Rotate", "R", "rotate"),
    item("Scale", "T", "scale"),
    section("PLACEMENT TOOLS"),
    item("Placement Tool", None, "placement"),
    item("Dynamic Place", None, "dynamic_place"),
    item("Scatter Pen", None, "scatter_pen"),
    section("TRANSFORM"),
    item("Reset Transformation", "Alt+0, Ctrl+Alt+0", "m_reset_transform", False),
    item("Freeze Transformation", None, "m_freeze", False),
    item("Unfreeze Transformation", None, "m_unfreeze", False),
    sub("Axis", [
        item("Center Axis To"),
        item("Center Object to Axis"),
        item("Axis to Parent Center"),
        SEP,
        item("Reset Axis"),
    ]),
    section("ARRANGE"),
    item("Arrange", None, "m_arrange", False),
    item("Center", None, "m_center", False),
    item("Duplicate", None, "m_duplicate", False),
    item("Transfer", None, "m_transfer", False),
    item("Randomize", None, "m_randomize", False),
    item("Replace With", None, "m_replace", False, gear=True),
    item("Project Object", None, "m_project_object", False, gear=True),
    section("EXTRA"),
    item("Paint Tool", None, "paint_brush"),
    item("Naming Tool", None, "m_naming"),
    item("Annotation Tool", None, "m_annotation"),
    sub("Guide", [
        item("Guide", None, "guide"),
        item("Guide Tool", None, "guide"),
        item("Delete Enabled Guides"),
        SEP,
        item("Measure and Construct", None, "measure"),
    ]),
    sub("Doodle", [
        item("Doodle Paint", None, "sketch"),
        item("Doodle Eraser", None, "sketch_eraser"),
        SEP,
        item("Add Doodle Frame"),
        item("Duplicate Doodle Frame"),
        item("Clear Doodle Frame"),
        item("Remove Doodle Frame"),
        SEP,
        item("Set Doodle Viewport"),
    ]),
    sub("Convert", [
        item("Make Editable", "C", "make_editable"),
        item("Current State to Object"),
        item("Connect Objects", None, "connect_objects"),
        item("Connect Objects + Delete"),
    ]),
]


SPLINE = [
    section("CREATE"),
    item("Spline Pen", None, "spline_pen"),
    item("Sketch", None, "sketch"),
    item("Spline Smooth", None, "spline_smooth"),
    item("Spline Arc Tool", None, "spline_arc"),
    section("BOOLEANS"),
    item("Spline Subtract", None, None, False),
    item("Spline Union", None, None, False),
    item("Spline And", None, None, False),
    item("Spline Or", None, None, False),
    item("Spline Intersect", None, None, False),
    section("EDIT"),
    item("Chamfer", None, None, False),
    item("Create Outline...", None, None, False),
    item("Project Spline...", None, None, False),
    item("Break Segment", None, None, False),
    item("Join Segment", None, None, False),
    item("Reverse Sequence", None, None, False),
    SEP,
    item("Set First Point", None, None, False),
    item("Round...", None, None, False),
]


MESH_MENU = [
    section("CONVERSION"),
    item("Make Editable", "C", "make_editable"),
    item("Current State to Object"),
    item("Connect Objects", None, "connect_objects"),
    item("Connect Objects + Delete"),
    section("CREATION TOOLS"),
    item("Polygon Pen", "M~E", "polygon_pen"),
    item("Bevel", "M~S"),
    item("Extrude", "M~T"),
    item("Inset", "M~W"),
    item("Matrix Extrude"),
    item("Thicken"),
    item("Trunk"),
    item("Bridge", "M~B"),
    item("Stitch and Sew", "M~P"),
    item("Weld", "M~Q"),
    item("Close Polygon Hole", "M~D"),
    section("CUT"),
    item("Line Cut", "K~K"),
    item("Loop/Path Cut", "K~L"),
    item("Plane Cut", "K~J"),
    item("Edge Cut", "M~F"),
    section("TRANSFORM"),
    item("Slide", "M~O"),
    item("Smooth Shift"),
    item("Equal Spacing"),
    item("Straighten Edges"),
    item("Fit Circle"),
    item("Flatten"),
    SEP,
    sub("Commands", _plain([
        "Connect Points/Edges", "Split", "Disconnect", "Triangulate",
        "Untriangulate", "Subdivide", "Melt", "Split Polygons",
        "Spin Edge", "Set Flow",
    ])),
    sub("Normals", _plain(["Align Normals", "Reverse Normals"])),
    SEP,
    item("Volume Mesh..."),
]


VOLUME = [
    item("Volume Builder", None, "volume_builder"),
    item("Volume Mesher", None, "volume_mesher"),
    item("Volume Mesh..."),
    item("Volume Loader"),
    section("SDF"),
    item("SDF Smooth", None, "sdf"),
    item("SDF Dilate and Erode", None, "sdf"),
    item("SDF Close and Open", None, "sdf"),
    section("FOG"),
    item("Fog Smooth", None, "fog"),
    item("Fog Multiply", None, "fog"),
    item("Fog Invert", None, "fog"),
    item("Fog Add", None, "fog"),
    item("Fog Range Map", None, "fog"),
    item("Fog Curve", None, "fog"),
    section("VECTOR"),
    item("Vector Smooth", None, "vector"),
    item("Vector Scale", None, "vector"),
    item("Vector Rotate", None, "vector"),
    item("Vector Invert", None, "vector"),
    item("Vector Normalize", None, "vector"),
    item("Vector Curl", None, "vector"),
]


MOGRAPH = [
    section("GENERATORS"),
    item("Cloner", None, "cloner"),
    item("Matrix", None, "generator"),
    item("Fracture", None, "generator"),
    item("Voronoi Fracture", None, "voronoi"),
    item("Text", None, "text"),
    item("Tracker", None, "generator"),
    item("MoSpline", None, "spline"),
    item("MoExtrude", None, "generator"),
    item("MoInstance", None, "generator"),
    section("EFFECTORS"),
    sub("Effector", [
        item("Group", None, "m_effector"),
        item("Simple", None, "m_effector"),
        item("Delay", None, "m_effector"),
        item("Formula", None, "m_effector"),
        item("Inheritance", None, "m_effector"),
        item("Random", None, "m_effector"),
        item("Shader", None, "m_effector"),
        item("Sound", None, "m_effector"),
        item("Step", None, "m_effector"),
        item("Time", None, "m_effector"),
        SEP,
        item("Target", None, "m_effector"),
        item("Volume", None, "m_effector"),
        item("Push Apart", None, "m_effector"),
        item("ReEffector", None, "m_effector"),
        item("Spline", None, "m_effector"),
        item("Python", None, "m_effector"),
    ]),
    sub("Field", _FIELDS),
    section("SELECTION"),
    item("MoGraph Selection"),
    item("MoGraph Weight Paint Brush"),
    item("MoGraph Cache Tag", None, "tag"),
    SEP,
    item("Link Cloners to Active Effector", None, None, False),
]


CHARACTER_MENU = [
    section("JOINTS"),
    item("Joint Tool", None, "joint"),
    item("Joint", None, "joint"),
    item("Joint Align", None, None, False),
    item("Mirror Joints", None, None, False),
    section("SKIN"),
    item("Link", None, None, False),
    item("Weight Tool", None, "weight"),
    item("Weight Manager"),
    item("Skin", None, "deformer"),
    section("CONSTRAINTS"),
    item("Constraint"),
    item("IK Tag", None, "tag"),
    item("Pose Morph Tag", None, "pose_morph"),
    section("CHARACTER"),
    item("Character"),
    item("Character Component"),
    item("CMotion"),
    SEP,
    sub("Commands", _plain([
        "Create IK Chain", "Remove IK", "Convert to Joints",
        "Normalize Weights", "Mirror Weights",
    ])),
    sub("Managers", _plain(["Weight Manager", "Constraint Manager"])),
]


ANIMATE_MENU = [
    section("RECORDING"),
    item("Record Active Objects", "F9"),
    item("Autokeying", "Ctrl+F9"),
    item("Add Parameter Keys"),
    section("PLAYBACK"),
    item("Go to Start", "Shift+G"),
    item("Go to Previous Frame", ","),
    item("Play Backwards", "F6"),
    item("Play Forwards", "F8"),
    item("Go to Next Frame", "."),
    item("Go to End", "Shift+F"),
    sub("Playback Mode", [
        item("Simple"),
        item("Loop", check=True),
        item("Ping-Pong"),
    ]),
    section("TOOLS"),
    item("Make Preview…"),
    item("Bake Objects..."),
    item("Add Motion Clip..."),
    sub("Point Level Animation", _plain([
        "Record Points", "Record Point Selection", "Clear Points",
    ])),
]


SIMULATE_MENU = [
    item("Simulation Scene"),
    section("SIMULATION"),
    sub("Cloth", _plain(["Cloth Tag", "Rope Tag", "Belt Tag", None,
                          "Cloth Generator"], "tag")),
    sub("Bodies", _plain(["Rigid Body Tag", "Soft Body Tag", "Collider Tag"], "tag")),
    sub("Pyro", _plain(["Pyro Emitter", "Pyro Fuel Tag", "Pyro Output"])),
    sub("Particles", _plain(["Emitter", "Particle Group", None, "Follow Position",
                              "Inheritance", "Speed Limit"])),
    sub("Forces", _plain(["Attractor", "Deflector", "Drag", "Friction", "Gravity",
                          "Rotation", "Turbulence", "Wind"])),
    section("CACHE"),
    item("Bake Simulation", None, None, False),
    item("Clear Cache", None, None, False),
    SEP,
    item("Simulation Settings..."),
]


TRACKER_MENU = [
    item("Motion Tracker", None, "camera"),
    item("Object Tracker"),
    item("Camera Calibrator", None, "camera"),
    section("TRACKING"),
    item("Auto Track", None, None, False),
    item("Manual Track", None, None, False),
    item("3D Camera Solver", None, None, False),
    section("CONSTRAINTS"),
    item("Create Position Constraint", None, None, False),
    item("Create Vector Constraint", None, None, False),
    item("Create Plane Constraint", None, None, False),
    SEP,
    item("Create User Asset", None, None, False),
]


RENDER_MENU = [
    item("Render Active View", "Ctrl+R", "render_view"),
    item("Render Region", None, "render_region"),
    item("Interactive Render Region", "Alt+R", "render_region"),
    item("Render to Picture Viewer", "Shift+R", "render_view"),
    item("Team Render to Picture Viewer..."),
    section("TAKES"),
    item("Render All Takes", None, "take"),
    item("Render Marked Takes", None, "take"),
    item("Team Render All Takes"),
    item("Team Render Marked Takes"),
    section("QUEUE"),
    item("Add to Render Queue...", None, "render_queue"),
    item("Render Queue", None, "render_queue"),
    item("Make Preview…"),
    section("SETTINGS"),
    item("Edit Render Settings...", "Ctrl+B", "render_settings"),
    sub("Render Settings", [
        item("My Render Settings", check=True),
        SEP,
        item("New Setting"),
        item("Manage Settings..."),
    ]),
    item("Share Machine over Network"),
    item("Team Render Machines..."),
]


REDSHIFT = [
    item("RS RenderView", None, "render_view"),
    item("Redshift Settings", None, "render_settings"),
    item("AOV Manager"),
    section("OBJECTS"),
    sub("Lights", _plain(["RS Area Light", "RS Point Light", "RS Spot Light",
                         "RS Infinite Light", "RS Dome Light", "RS Sun and Sky"], "light")),
    item("RS Proxy", None, "m_proxy"),
    item("RS BakeSet", None, "m_bake_set"),
    item("RS Volume", None, "volume_builder"),
    item("RS Environment", None, "environment"),
    section("MATERIALS"),
    item("RS Standard Material", None, "material"),
    item("Convert Scene Materials...", None, None, False),
    section("TOOLS"),
    item("Export Proxy...", None, None, False),
    item("Render Feedback"),
    item("Redshift Documentation"),
]


EXTENSIONS_MENU = [
    item("Script Manager", "Shift+F11", "python"),
    item("Console", "Shift+F10"),
    item("Execute Script..."),
    sub("User Scripts", [
        item("Open Script Folder"),
        item("Reload Scripts"),
    ]),
    SEP,
    item("Extension Manager..."),
    item("Reload Python Plugins"),
    SEP,
    sub("D5 Sync 3.0.0.0020", [
        item("Synchronize"),
        item("Settings..."),
        item("About D5 Sync"),
    ]),
]


WINDOW_MENU = [
    sub("Customization", [
        item("Customize Commands...", "Shift+F12"),
        item("Customize Palettes..."),
        item("New Icon Palette"),
        SEP,
        item("Save as Startup Layout"),
        item("Save Layout As..."),
        item("Load Layout..."),
    ]),
    item("Fullscreen Mode", "Ctrl+Tab", "m_fullscreen"),
    item("Fullscreen Mode (Group)", "Ctrl+Shift+Tab"),
    section("ASSETS"),
    item("Asset Browser", "Shift+F8", "m_asset_browser", popout=True),
    item("Project Asset Inspector", None, "m_asset_inspector"),
    section("OBJECTS"),
    item("Object Manager", "Shift+F1", "m_object_manager", checked=True, popout=True),
    item("Object Profiler", None, "m_profiler"),
    item("Node Editor", "Shift+Alt+F2", "m_node_editor", popout=True),
    item("Layer Manager", "Shift+F4", "layers"),
    SEP,
    item("Attribute Manager", "Shift+F5", "m_attribute_manager", checked=True, popout=True),
    item("Task Manager", None, "m_task_manager"),
    section("MATERIALS"),
    item("Material Manager", "Shift+F2", "m_material_manager"),
    item("Material Editor", None, "m_material_editor"),
    section("ANIMATION"),
    item("Timeline (Dope Sheet)", "Shift+F3", "m_timeline_dope", popout=True),
    item("Timeline (F-Curve)", "Shift+Alt+F3", "m_timeline_curve", popout=True),
    section("MODELING"),
    item("Coordinate Manager", "Shift+F7", "m_coordinates"),
    item("Structure Manager", "Shift+F9", "m_structure"),
    item("Sculpt Layers", None, "m_sculpt_layers"),
    section("RENDERING"),
    item("Take Manager", None, "m_take_manager"),
    item("Picture Viewer", "Shift+F6", "m_picture_viewer", popout=True),
    section("UV EDITING AND PAINTING"),
    item("UV Texture Editor", None, "m_uv_editor"),
    item("Color Settings", None, "m_color_settings"),
    item("Layer Manager", None, "m_uv_layers"),
    item("Projection Man", None, "m_projection"),
    SEP,
    item("Untitled", None, None, check=True),
]


HELP_MENU = [
    item("Show Help...", "Ctrl+F1"),
    item("Online Manual"),
    item("Search Commands...", "Shift+C", "search"),
    item("What's New in This Version"),
    item("Keyboard Shortcuts"),
    SEP,
    item("Check for Updates..."),
    item("Manage License..."),
    item("Report a Problem..."),
    SEP,
    item("About Quartz Studio..."),
]


MENU_BAR: list[tuple[str, list, str | None]] = [
    ("File", FILE_MENU, None),
    ("Edit", EDIT_MENU, None),
    ("Create", CREATE_MENU, "new"),
    ("Modes", MODES_MENU, None),
    ("Select", SELECT_MENU, None),
    ("Tools", TOOLS_MENU, None),
    ("Spline", SPLINE, None),
    ("Mesh", MESH_MENU, "new"),
    ("Volume", VOLUME, None),
    ("MoGraph", MOGRAPH, "new"),
    ("Character", CHARACTER_MENU, None),
    ("Animate", ANIMATE_MENU, None),
    ("Simulate", SIMULATE_MENU, None),
    ("Tracker", TRACKER_MENU, None),
    ("Render", RENDER_MENU, None),
    ("Redshift", REDSHIFT, None),
    ("Extensions", EXTENSIONS_MENU, None),
    ("Window", WINDOW_MENU, "new_pale"),
    ("Help", HELP_MENU, None),
]

MENU_TITLES: list[str] = [t for t, _e, _s in MENU_BAR]

LAYOUTS: list[str] = [
    "Startup", "Standard", "Model", "Sculpt", "UVEdit",
    "Paint", "Groom", "Track", "Script", "Nodes",
]
ACTIVE_LAYOUT = "Startup"

LAYOUT_MENU = [
    section("LAYOUTS"),
    *[item(name, None, None, check=(name == ACTIVE_LAYOUT)) for name in LAYOUTS],
    item("Animate"),
    item("Motion Tracker"),
    item("Visualize"),
    SEP,
    item("Save as Startup Layout"),
    item("Save Layout As..."),
    item("Load Layout..."),
    item("Reset Layout"),
    SEP,
    item("Show Layout Tabs", None, None, check=True),
]

DOCUMENT_TAB_MENU = [
    item("New Project", "Ctrl+N", "file_new"),
    item("Save Project", "Ctrl+S", "file_save"),
    SEP,
    item("Close Project", "Ctrl+F4"),
    item("Close Other Projects", None, None, False),
    SEP,
    item("Show in Explorer", None, None, False),
]
