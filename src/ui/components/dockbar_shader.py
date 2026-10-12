"""GLSL shader background renderer for DockBar (Liquid Glass & Glassy Ice with real screen refraction)."""
import time
from typing import Optional
from kivy.clock import Clock
from kivy.graphics import RenderContext, Rectangle, Callback
from kivy.graphics.texture import Texture
from kivy.graphics.opengl import glCopyTexSubImage2D, GL_TEXTURE_2D
from kivy.metrics import dp
from kivymd.app import MDApp
from kivy.utils import platform
from src.core.logger import logger

IS_MOBILE = platform in ("android", "ios")

SHADER_VS = """
#ifdef GL_ES
precision highp float;
#endif

varying vec4 frag_color;
varying vec2 tex_coord0;

attribute vec2 vPosition;
attribute vec2 vTexCoords0;

uniform mat4 modelview_mat;
uniform mat4 projection_mat;
uniform vec4 color;
uniform float opacity;

void main(void) {
    frag_color = color * vec4(1.0, 1.0, 1.0, opacity);
    tex_coord0 = vTexCoords0;
    gl_Position = projection_mat * modelview_mat * vec4(vPosition.xy, 0.0, 1.0);
}
"""

LIQUID_GLASS_FS = """
#ifdef GL_ES
precision highp float;
#endif

varying vec4 frag_color;
varying vec2 tex_coord0;

uniform sampler2D texture0;
uniform vec2 resolution;
uniform float time;
uniform vec4 u_capsule; // local x, y, w, h
uniform float u_radius;
uniform float u_style;  // 0: impact, 1: telegram, 2: incy, 3: pinterest
uniform vec4 u_island1; // local x, y, w, h for pinterest dialogs
uniform vec4 u_island2; // local x, y, w, h for pinterest logs
uniform vec4 u_island3; // local x, y, w, h for pinterest settings
uniform vec4 u_accent;
uniform vec4 u_surface_color;
uniform float u_is_dark;

void main(void) {
    vec2 p = tex_coord0 * resolution;

    // Fast analytical box selection (Impact/Telegram/Incy capsule or Pinterest islands)
    vec4 island;
    if (u_style > 2.5) {
        float d1 = abs(p.x - (u_island1.x + u_island1.z * 0.5));
        float d2 = abs(p.x - (u_island2.x + u_island2.z * 0.5));
        float d3 = abs(p.x - (u_island3.x + u_island3.z * 0.5));
        island = (d1 < d2 && d1 < d3) ? u_island1 : ((d2 < d3) ? u_island2 : u_island3);
    } else {
        island = u_capsule;
    }

    vec2 center = island.xy + island.zw * 0.5;
    vec2 half_size = island.zw * 0.5;
    vec2 offset = p - center;
    vec2 q = abs(offset) - half_size + vec2(u_radius);
    float dist = min(max(q.x, q.y), 0.0) + length(max(q, vec2(0.0))) - u_radius;

    // Anti-aliased outer edge mask
    float alpha = 1.0 - smoothstep(0.0, 1.5, dist);

    float depth = max(-dist, 0.0);

    // Exact analytical outward normal (0 finite-difference SDF calls, 4x faster)
    vec2 edge_grad = normalize(max(q, vec2(0.0001))) * sign(offset);

    // Curvature radius R for each style:
    // Impact: 14px edge bevel
    // Telegram: capsule height / 2 (29px)
    // Incy: 16px corner bevel
    // Pinterest: 27px island radius
    float R = (u_style < 0.5) ? 14.0 : max(u_radius, 1.0);
    float t = clamp(depth / R, 0.0, 1.0);

    // Smooth convex lens slope (0 in flat center, 1 at edge)
    float slope = sin((1.0 - t) * 1.5707963);

    // Physical lens displacement: points near edge bend inwards towards lens center
    vec2 refr = -edge_grad * slope * (6.0 / max(resolution, vec2(1.0)));

    // Subtle natural chromatic dispersion (approx 1.8% dispersion)
    vec2 uv_r = clamp(tex_coord0 + refr * 1.018, 0.002, 0.998);
    vec2 uv_g = clamp(tex_coord0 + refr, 0.002, 0.998);
    vec2 uv_b = clamp(tex_coord0 + refr * 0.982, 0.002, 0.998);

    // Optical sampling of background
    float r = texture2D(texture0, uv_r).r;
    float g = texture2D(texture0, uv_g).g;
    float b = texture2D(texture0, uv_b).b;
    vec3 col = vec3(r, g, b);

    // Normalized coordinates across capsule/dockbar for subtle depth
    vec2 norm_pos = (p - u_capsule.xy) / max(u_capsule.zw, vec2(1.0));
    norm_pos = clamp(norm_pos, 0.0, 1.0);

    // Pure transparent optical glass body
    if (u_is_dark > 0.5) {
        col = mix(col, col * 0.93 + vec3(0.01, 0.02, 0.04), 0.08);
        float bottom_ao = smoothstep(12.0, 0.0, depth) * smoothstep(0.55, 0.0, norm_pos.y);
        col *= (1.0 - bottom_ao * 0.12);
    } else {
        col = mix(col, vec3(0.98, 0.99, 1.0), 0.05);
        float bottom_ao = smoothstep(12.0, 0.0, depth) * smoothstep(0.55, 0.0, norm_pos.y);
        col *= (1.0 - bottom_ao * 0.08);
    }

    // Crisp 1.2px glass rim outline
    float rim = smoothstep(1.3, 0.0, abs(dist));
    float rim_direction = 0.35 + 0.65 * max(0.0, -edge_grad.y);
    float rim_intensity = rim * 0.45 * rim_direction;

    // Hairline top bevel gleam
    float top_bevel = smoothstep(2.5, 0.8, depth) * smoothstep(0.0, 0.8, depth) * max(0.0, -edge_grad.y);
    col += vec3(1.0) * top_bevel * 0.18;

    // Apply clean glass rim
    col = mix(col, vec3(1.0), rim_intensity);

    // Hardware alpha blending (Early-Z compatible, no discard)
    gl_FragColor = vec4(col, alpha);
}
"""

GLASSY_ICE_FS = """
#ifdef GL_ES
precision highp float;
#endif

varying vec4 frag_color;
varying vec2 tex_coord0;

uniform sampler2D texture0;
uniform vec2 resolution;
uniform float time;
uniform vec4 u_capsule; // local x, y, w, h
uniform float u_radius;
uniform float u_style;  // 0: impact, 1: telegram, 2: incy, 3: pinterest
uniform vec4 u_island1; // local x, y, w, h
uniform vec4 u_island2;
uniform vec4 u_island3;
uniform vec4 u_accent;
uniform vec4 u_surface_color;
uniform float u_is_dark;

vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453);
}

float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash12(i + vec2(0.0, 0.0)), hash12(i + vec2(1.0, 0.0)), u.x),
        mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), u.x),
        u.y
    );
}

// 3x3 single-pass Voronoi (9 iterations total, 60fps mobile optimized)
vec3 voronoi(vec2 x) {
    vec2 n = floor(x);
    vec2 f = fract(x);
    vec2 mg = vec2(0.0);
    vec2 mr = vec2(0.0);
    float md1 = 8.0;
    float md2 = 8.0;

    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 g = vec2(float(i), float(j));
            vec2 o = hash2(n + g);
            vec2 r = g + o - f;
            float d = dot(r, r);
            if (d < md1) {
                md2 = md1;
                md1 = d;
                mr = r;
                mg = g;
            } else if (d < md2) {
                md2 = d;
            }
        }
    }
    float d_edge = (sqrt(md2) - sqrt(md1)) * 0.5;
    return vec3(sqrt(md1), d_edge, n.x + mg.x + (n.y + mg.y) * 57.0);
}

void main(void) {
    vec2 p_loc = tex_coord0 * resolution;

    // Fast analytical box selection
    vec4 island;
    if (u_style > 2.5) {
        float d1 = abs(p_loc.x - (u_island1.x + u_island1.z * 0.5));
        float d2 = abs(p_loc.x - (u_island2.x + u_island2.z * 0.5));
        float d3 = abs(p_loc.x - (u_island3.x + u_island3.z * 0.5));
        island = (d1 < d2 && d1 < d3) ? u_island1 : ((d2 < d3) ? u_island2 : u_island3);
    } else {
        island = u_capsule;
    }

    vec2 center = island.xy + island.zw * 0.5;
    vec2 half_size = island.zw * 0.5;
    vec2 offset = p_loc - center;
    vec2 q = abs(offset) - half_size + vec2(u_radius);
    float dist = min(max(q.x, q.y), 0.0) + length(max(q, vec2(0.0))) - u_radius;

    float alpha = 1.0 - smoothstep(0.0, 1.5, dist);

    // 3x3 Voronoi cell facets
    vec2 p = (p_loc - u_capsule.xy) / 46.0;
    vec3 v = voronoi(p);
    float d_edge = v.y;
    float cell_id = v.z;

    // Per-facet tilt: shifts each crystal shard independently
    vec2 facet_tilt = (hash2(vec2(cell_id, cell_id * 1.337)) - 0.5) * 0.38;

    // Fast procedural crystalline frost noise
    float frost_noise = vnoise(p_loc / 11.0);
    float fine_grain = hash12(p_loc * 0.85);

    // Micro-relief bump from frost noise
    vec2 frost_bump = (vec2(fine_grain, hash12(p_loc * 0.85 + 17.1)) - 0.5) * 0.04;

    // Surface normal combining crystal facet tilt and micro-frost bump
    vec3 N = normalize(vec3(facet_tilt * 0.65 + frost_bump * 0.40, 1.0));

    // Internal fracture plane refractive jump
    float edge_factor = 1.0 - smoothstep(0.0, 0.055, d_edge);
    vec2 fracture_refr = normalize(facet_tilt + vec2(0.14, 0.09)) * edge_factor * 0.035;

    // Facet background displacement
    vec2 facet_disp = (hash2(vec2(cell_id, cell_id * 1.618)) - 0.5) * 0.075;

    // Base refracted coordinates
    vec2 base_uv = tex_coord0 + facet_disp + fracture_refr + frost_bump * 0.020;

    // Chromatic dispersion offsets through ice prism
    vec2 disp_r = vec2( 0.010,  0.004) + frost_bump * 0.012;
    vec2 disp_b = vec2(-0.010, -0.004) - frost_bump * 0.012;

    // Frosted scattering (3 dispersive taps + 1 frosted scatter tap)
    float r = texture2D(texture0, clamp(base_uv + disp_r, 0.002, 0.998)).r;
    float g = texture2D(texture0, clamp(base_uv, 0.002, 0.998)).g;
    float b = texture2D(texture0, clamp(base_uv + disp_b, 0.002, 0.998)).b;
    vec3 col = vec3(r, g, b);

    // Soft crystalline frost blur tap
    vec2 scatter_uv = base_uv + (vec2(fine_grain, hash12(p_loc * 0.5)) - 0.5) * (6.0 / max(resolution, vec2(1.0)));
    vec3 scatter_col = texture2D(texture0, clamp(scatter_uv, 0.002, 0.998)).rgb;
    col = mix(col, scatter_col, 0.35);

    // Uniform icy tinting
    if (u_is_dark > 0.5) {
        col = mix(col, col * vec3(0.92, 0.96, 1.04) + vec3(0.06, 0.09, 0.14), 0.18);
    } else {
        col = mix(col, col * vec3(0.96, 0.98, 1.02) + vec3(0.09, 0.12, 0.16), 0.16);
    }

    // Surface frost tactile film ("шум" на поверхности)
    float frost_grain = (frost_noise - 0.5) * 0.08 + (fine_grain - 0.5) * 0.04;
    col += vec3(0.85, 0.94, 1.0) * frost_grain;

    // Specular lighting & sparkling glints
    vec3 L = normalize(vec3(0.30, 0.85, 0.55));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 22.0) * 0.35;
    float sparkle = pow(max(dot(N, H), 0.0), 48.0) * 0.75 * smoothstep(0.42, 0.75, frost_noise);
    col += (vec3(0.90, 0.96, 1.0) * spec + vec3(1.0) * sparkle);

    // Capsule outer rim highlight
    float edge_depth = max(-dist, 0.0);
    float rim = smoothstep(2.6, 0.6, edge_depth) * smoothstep(0.0, 0.6, edge_depth);
    float edge_aa = smoothstep(1.5, 0.0, abs(dist));
    col += vec3(0.85, 0.95, 1.0) * rim * 0.35;
    col = mix(col, vec3(1.0), edge_aa * 0.22);

    // Delicate icy shimmer
    float shimmer = sin(time * 0.7 + cell_id * 0.3) * 0.020;
    col += vec3(0.5, 0.8, 1.0) * max(shimmer, 0.0);

    // Hardware alpha blending (Early-Z compatible, no discard)
    gl_FragColor = vec4(col, alpha);
}
"""

# Keep mobile aliases pointing to the unified high-performance shaders
LIQUID_GLASS_MOBILE_FS = LIQUID_GLASS_FS
GLASSY_ICE_MOBILE_FS = GLASSY_ICE_FS


class DockbarShaderRenderer:
    """Manages GLSL procedural shader rendering with live background refraction for DockBar."""

    def __init__(self, dockbar):
        self.dockbar = dockbar
        self.render_context: Optional[RenderContext] = None
        self.rect: Optional[Rectangle] = None
        self.bg_texture: Optional[Texture] = None
        self.callback: Optional[Callback] = None
        self.current_bg_type: str = "theme"
        self._clock_event = None
        self._start_time = time.time()
        self._init_done = False

    def init_gl(self):
        """Initializes RenderContext lazily when OpenGL context is ready."""
        if self._init_done:
            return True

        try:
            rc = RenderContext(use_parent_projection=True, use_parent_modelview=True)
            rc.shader.vs = SHADER_VS

            w = max(1, int(self.dockbar.width or dp(300)))
            h = max(1, int(self.dockbar.height or dp(78)))
            self.bg_texture = Texture.create(size=(w, h), colorfmt="rgba")
            self.callback = Callback(self._capture_framebuffer)
            rc.add(self.callback)
            with rc:
                self.rect = Rectangle(texture=self.bg_texture, pos=self.dockbar.pos, size=self.dockbar.size)

            self.render_context = rc
            # Insert at beginning of canvas.before so it draws behind dock items
            self.dockbar.canvas.before.insert(0, rc)
            self._init_done = True
            logger.info("DockbarShaderRenderer initialized RenderContext successfully (is_mobile=%s)", IS_MOBILE)
            return True
        except Exception as e:
            logger.warning("DockbarShaderRenderer could not initialize RenderContext: %s", e)
            return False

    def _capture_framebuffer(self, instr):
        """Copies rendered screen pixels behind the dockbar into bg_texture for refraction."""
        if not self.bg_texture or self.current_bg_type == "theme":
            return
        dockbar = self.dockbar
        try:
            from kivy.core.window import Window

            win_pos = dockbar.to_window(dockbar.x, dockbar.y)
            win_x = int(win_pos[0])
            win_y = int(win_pos[1])
            w = max(1, int(dockbar.width))
            h = max(1, int(dockbar.height))

            win_w = int(Window.width)
            win_h = int(Window.height)

            # Clamp safely within window bounds to prevent GL_INVALID_VALUE on mobile GLES
            clamped_x = max(0, min(win_x, win_w - 1))
            clamped_y = max(0, min(win_y, win_h - 1))
            copy_w = max(1, min(w, win_w - clamped_x))
            copy_h = max(1, min(h, win_h - clamped_y))

            if self.bg_texture.size != (copy_w, copy_h):
                self.bg_texture = Texture.create(size=(copy_w, copy_h), colorfmt="rgba")
                if self.rect:
                    self.rect.texture = self.bg_texture

            self.bg_texture.bind()
            glCopyTexSubImage2D(
                GL_TEXTURE_2D, 0, 0, 0,
                clamped_x, clamped_y,
                copy_w, copy_h
            )
        except Exception:
            pass

    def update_shader(self, bg_type: str):
        """Switches between 'theme', 'liquid_glass', and 'glassy_ice'."""
        self.current_bg_type = bg_type or "theme"

        if self.current_bg_type == "theme":
            if self._clock_event:
                self._clock_event.cancel()
                self._clock_event = None
            if self.rect:
                self.rect.size = (0, 0)
            return

        if not self._init_done:
            if not self.init_gl():
                return

        if not self.render_context:
            return

        if self.current_bg_type == "liquid_glass":
            self.render_context.shader.fs = LIQUID_GLASS_FS
            if self._clock_event:
                self._clock_event.cancel()
                self._clock_event = None
        elif self.current_bg_type == "glassy_ice":
            self.render_context.shader.fs = GLASSY_ICE_FS
            if self._clock_event is None:
                self._clock_event = Clock.schedule_interval(self._on_tick, 1.0 / 20.0)
        else:
            return

        if not self.render_context.shader.success:
            logger.error("Dockbar shader compilation failed for %s", self.current_bg_type)
            return

        self.update_geometry()

    def update_geometry(self, *args):
        """Updates geometry and uniforms for current dockbar style and position."""
        if not self.render_context or self.current_bg_type == "theme":
            return

        dockbar = self.dockbar
        app = MDApp.get_running_app()
        if not app:
            return

        if self.rect:
            self.rect.pos = dockbar.pos
            self.rect.size = dockbar.size

        style_str = getattr(app, "dockbar_style", "impact")
        style_map = {"impact": 0, "telegram": 1, "incy": 2, "pinterest": 3}
        u_style = style_map.get(style_str, 0)

        pad_x = float(dp(16))
        pad_y = float(dp(10))
        if u_style == 0:  # impact
            cap_x = 0.0
            cap_y = 0.0
            cap_w = float(dockbar.width)
            cap_h = float(dockbar.height)
            radius = 0.0
        elif u_style == 1:  # telegram
            cap_x = pad_x
            cap_y = pad_y
            cap_w = max(1.0, float(dockbar.width) - pad_x * 2.0)
            cap_h = max(1.0, float(dockbar.height) - pad_y * 2.0)
            radius = float(cap_h / 2.0)
        elif u_style == 2:  # incy
            cap_x = pad_x
            cap_y = pad_y
            cap_w = max(1.0, float(dockbar.width) - pad_x * 2.0)
            cap_h = max(1.0, float(dockbar.height) - pad_y * 2.0)
            radius = float(dp(16))
        else:  # pinterest
            cap_x = 0.0
            cap_y = 0.0
            cap_w = float(dockbar.width)
            cap_h = float(dockbar.height)
            sel = getattr(app, "dockbar_selection", "squares")
            radius = float(dp(27) if sel == "circles" else dp(16))

        rc = self.render_context
        rc["u_style"] = float(u_style)
        rc["u_capsule"] = [float(cap_x), float(cap_y), float(cap_w), float(cap_h)]
        rc["u_radius"] = float(radius)

        btn_sz = float(dp(54))
        pad_pinterest = max(float(dp(16)), (float(dockbar.width) - float(dp(190))) / 2.0)
        for i, item_id in enumerate(["item_dialogs", "item_logs", "item_settings"], 1):
            item = dockbar.ids.get(item_id) if hasattr(dockbar, "ids") else None
            if item and item.width > dp(10):
                cx = float(item.center_x - dockbar.x)
                cy = float(item.center_y - dockbar.y)
            else:
                cx = float(pad_pinterest + btn_sz / 2.0 + (i - 1) * (btn_sz + float(dp(14))))
                cy = float(dockbar.height / 2.0)
            rc[f"u_island{i}"] = [float(cx - btn_sz / 2.0), float(cy - btn_sz / 2.0), btn_sz, btn_sz]

        accent = getattr(app, "accent_color", [0.24, 0.48, 0.95, 1.0])
        rc["u_accent"] = [float(c) for c in accent[:4]]

        surface = getattr(app, "surface_color", [1.0, 1.0, 1.0, 1.0])
        rc["u_surface_color"] = [float(c) for c in surface[:4]]

        is_dark = 1.0 if getattr(app, "theme_mode", "light") in ("dark", "amoled") else 0.0
        rc["u_is_dark"] = float(is_dark)
        rc["resolution"] = [float(dockbar.width), float(dockbar.height)]

    def _on_tick(self, dt):
        """Animation update tick."""
        if not self.render_context or self.current_bg_type == "theme":
            return
        elapsed = time.time() - self._start_time
        self.render_context["time"] = float(elapsed)
        self.dockbar.canvas.ask_update()
