"""GLSL shader background renderer for DockBar (Liquid Glass & Glassy Ice with real screen refraction)."""
import time
from typing import Optional
from kivy.clock import Clock
from kivy.graphics import RenderContext, Rectangle, Callback
from kivy.graphics.texture import Texture
from kivy.graphics.opengl import glCopyTexSubImage2D, GL_TEXTURE_2D
from kivy.metrics import dp
from kivymd.app import MDApp
from src.core.logger import logger

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
uniform vec4 u_capsule; // x, y, w, h
uniform float u_radius;
uniform int u_style;    // 0: impact, 1: telegram, 2: incy, 3: pinterest
uniform vec4 u_island1; // x, y, w, h for pinterest dialogs
uniform vec4 u_island2; // x, y, w, h for pinterest logs
uniform vec4 u_island3; // x, y, w, h for pinterest settings
uniform vec4 u_accent;
uniform vec4 u_surface_color;
uniform float u_is_dark;

float roundedBoxSDF(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

float getDist(vec2 coord) {
    if (u_style == 3) {
        float d1 = roundedBoxSDF(coord - (u_island1.xy + u_island1.zw * 0.5), u_island1.zw * 0.5, u_radius);
        float d2 = roundedBoxSDF(coord - (u_island2.xy + u_island2.zw * 0.5), u_island2.zw * 0.5, u_radius);
        float d3 = roundedBoxSDF(coord - (u_island3.xy + u_island3.zw * 0.5), u_island3.zw * 0.5, u_radius);
        return min(min(d1, d2), d3);
    } else {
        return roundedBoxSDF(coord - (u_capsule.xy + u_capsule.zw * 0.5), u_capsule.zw * 0.5, u_radius);
    }
}

void main(void) {
    float dist = getDist(gl_FragCoord.xy);

    // Anti-aliased outer edge mask
    float alpha = 1.0 - smoothstep(0.0, 1.5, dist);
    if (alpha <= 0.001) discard;

    vec2 texel = 1.0 / max(resolution, vec2(1.0));

    // Normal calculation from SDF gradient at the glass bevel
    vec2 eps = vec2(1.0, 0.0);
    float d_dx = getDist(gl_FragCoord.xy + eps.xy) - getDist(gl_FragCoord.xy - eps.xy);
    float d_dy = getDist(gl_FragCoord.xy + eps.yx) - getDist(gl_FragCoord.xy - eps.yx);
    vec2 edge_grad = normalize(vec2(d_dx, d_dy) + vec2(0.0001));

    float edge_depth = max(-dist, 0.0);
    float bevel_t = clamp(edge_depth / 6.0, 0.0, 1.0);
    float bevel_curve = cos(bevel_t * 1.57079); // 1.0 at edge, 0.0 inside

    // Subtle edge lens refraction
    vec2 edge_refr = -edge_grad * bevel_curve * 5.0 * texel;

    // Multi-tap frosted glass blur (17 samples)
    vec2 base_uv = clamp(tex_coord0 + edge_refr, 0.002, 0.998);
    vec3 blurred = texture2D(texture0, base_uv).rgb * 0.18;

    float r1 = 3.5;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.0,  1.0) * r1 * texel, 0.002, 0.998)).rgb * 0.065;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.0, -1.0) * r1 * texel, 0.002, 0.998)).rgb * 0.065;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 1.0,  0.0) * r1 * texel, 0.002, 0.998)).rgb * 0.065;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-1.0,  0.0) * r1 * texel, 0.002, 0.998)).rgb * 0.065;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.707,  0.707) * r1 * texel, 0.002, 0.998)).rgb * 0.055;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.707,  0.707) * r1 * texel, 0.002, 0.998)).rgb * 0.055;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.707, -0.707) * r1 * texel, 0.002, 0.998)).rgb * 0.055;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.707, -0.707) * r1 * texel, 0.002, 0.998)).rgb * 0.055;

    float r2 = 7.0;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.38,  0.92) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.38,  0.92) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.38, -0.92) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.38, -0.92) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.92,  0.38) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.92,  0.38) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2( 0.92, -0.38) * r2 * texel, 0.002, 0.998)).rgb * 0.045;
    blurred += texture2D(texture0, clamp(base_uv + vec2(-0.92, -0.38) * r2 * texel, 0.002, 0.998)).rgb * 0.045;

    // Specular rim calculation (Apple iOS 18 Control Center style)
    vec2 light_dir_2d = normalize(vec2(-0.30, 0.95));
    float light_align = max(0.0, dot(-edge_grad, light_dir_2d));
    float rim_bright = 0.45 + 0.55 * light_align;

    float inner_rim = smoothstep(2.8, 0.6, edge_depth) * smoothstep(0.0, 0.6, edge_depth);
    float edge_aa = smoothstep(1.5, 0.0, abs(dist));

    // Translucent glass tint & gradient
    float v_norm = clamp((gl_FragCoord.y - u_capsule.y) / max(u_capsule.w, 1.0), 0.0, 1.0);
    vec3 col = vec3(0.0);

    if (u_is_dark > 0.5) {
        // Dark mode: smoky frosted acrylic glass
        vec3 glass_tint = vec3(0.16, 0.18, 0.22) + vec3(0.05, 0.05, 0.07) * v_norm;
        col = mix(blurred, glass_tint, 0.52);
        col += vec3(1.0) * inner_rim * rim_bright * 0.35;
        col = mix(col, vec3(1.0), edge_aa * 0.20 * rim_bright);
    } else {
        // Light mode: milky frosted liquid glass
        vec3 glass_tint = vec3(0.95, 0.96, 0.98) + vec3(0.03, 0.03, 0.03) * v_norm;
        col = mix(blurred, glass_tint, 0.56);
        col += vec3(1.0) * inner_rim * rim_bright * 0.45;
        col = mix(col, vec3(1.0), edge_aa * 0.32 * rim_bright);
    }

    // Subtle breathing satin sheen
    float sheen = sin(time * 0.6) * 0.015;
    col += vec3(sheen);

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
uniform vec4 u_capsule;
uniform float u_radius;
uniform int u_style;
uniform vec4 u_island1;
uniform vec4 u_island2;
uniform vec4 u_island3;
uniform vec4 u_accent;
uniform vec4 u_surface_color;
uniform float u_is_dark;

float roundedBoxSDF(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + vec2(r);
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

float getDist(vec2 coord) {
    if (u_style == 3) {
        float d1 = roundedBoxSDF(coord - (u_island1.xy + u_island1.zw * 0.5), u_island1.zw * 0.5, u_radius);
        float d2 = roundedBoxSDF(coord - (u_island2.xy + u_island2.zw * 0.5), u_island2.zw * 0.5, u_radius);
        float d3 = roundedBoxSDF(coord - (u_island3.xy + u_island3.zw * 0.5), u_island3.zw * 0.5, u_radius);
        return min(min(d1, d2), d3);
    } else {
        return roundedBoxSDF(coord - (u_capsule.xy + u_capsule.zw * 0.5), u_capsule.zw * 0.5, u_radius);
    }
}

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

float fbm(vec2 p) {
    float total = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        total += amp * vnoise(p);
        p = p * 2.05 + vec2(12.3, 34.5);
        amp *= 0.5;
    }
    return total;
}

// 2D Voronoi returning: (min_dist, dist_to_cell_edge, cell_id)
vec3 voronoi(vec2 x) {
    vec2 n = floor(x);
    vec2 f = fract(x);
    vec2 mg;
    vec2 mr;
    float md = 8.0;

    for (int j = -1; j <= 1; j++) {
        for (int i = -1; i <= 1; i++) {
            vec2 g = vec2(float(i), float(j));
            vec2 o = hash2(n + g);
            vec2 r = g + o - f;
            float d = dot(r, r);
            if (d < md) {
                md = d;
                mr = r;
                mg = g;
            }
        }
    }

    float md_edge = 8.0;
    for (int j = -2; j <= 2; j++) {
        for (int i = -2; i <= 2; i++) {
            vec2 g = mg + vec2(float(i), float(j));
            vec2 o = hash2(n + g);
            vec2 r = g + o - f;
            if (dot(mr - r, mr - r) > 0.0001) {
                float d_to_edge = dot(0.5 * (mr + r), normalize(r - mr));
                md_edge = min(md_edge, d_to_edge);
            }
        }
    }

    return vec3(sqrt(md), md_edge, n.x + mg.x + (n.y + mg.y) * 57.0);
}

void main(void) {
    float dist = getDist(gl_FragCoord.xy);

    float alpha = 1.0 - smoothstep(0.0, 1.5, dist);
    if (alpha <= 0.001) discard;

    vec2 texel = 1.0 / max(resolution, vec2(1.0));

    // Voronoi cell facets
    vec2 p = (gl_FragCoord.xy - u_capsule.xy) / 46.0;
    vec3 v = voronoi(p);
    float d_edge = v.y;
    float cell_id = v.z;

    // Per-facet tilt: shifts each crystal shard independently
    vec2 facet_tilt = (hash2(vec2(cell_id, cell_id * 1.337)) - 0.5) * 0.38;

    // Procedural crystalline frost noise ("шум" как на референсе)
    vec2 noise_uv = gl_FragCoord.xy / 11.0;
    float frost_noise = fbm(noise_uv);
    float fine_grain = hash12(gl_FragCoord.xy * 0.85);

    // Micro-relief bump from frost noise
    vec2 eps_n = vec2(0.85, 0.0);
    float n_x = fbm(noise_uv + eps_n.xy) - fbm(noise_uv - eps_n.xy);
    float n_y = fbm(noise_uv + eps_n.yx) - fbm(noise_uv - eps_n.yx);
    vec2 frost_bump = vec2(n_x, n_y) * 2.2;

    // Surface normal combining crystal facet tilt and micro-frost bump
    vec3 N = normalize(vec3(facet_tilt * 0.65 + frost_bump * 0.40, 1.0));

    // Transparent borders: internal fracture plane creates refractive jump & dispersion, NOT opaque white lines!
    float edge_factor = 1.0 - smoothstep(0.0, 0.055, d_edge);
    vec2 fracture_refr = normalize(facet_tilt + vec2(0.14, 0.09)) * edge_factor * 0.035;

    // Facet background displacement (breaks continuous text into disjoint shards)
    vec2 facet_disp = (hash2(vec2(cell_id, cell_id * 1.618)) - 0.5) * 0.075;

    // Frost scattering: diffuses underlying text so fine text is NOT clearly readable
    vec2 base_uv = tex_coord0 + facet_disp + fracture_refr + frost_bump * 0.020;
    float scatter_radius = 5.5 * texel.x;

    // Chromatic dispersion offsets through ice prism
    vec2 disp_r = vec2( 0.010,  0.004) + frost_bump * 0.012;
    vec2 disp_b = vec2(-0.010, -0.004) - frost_bump * 0.012;

    // Multi-tap frosted scattering (diffuses sharp letters into frosted crystalline glow)
    float r = texture2D(texture0, clamp(base_uv + disp_r, 0.002, 0.998)).r * 0.28;
    r += texture2D(texture0, clamp(base_uv + disp_r + vec2( 1.0,  0.0) * scatter_radius, 0.002, 0.998)).r * 0.18;
    r += texture2D(texture0, clamp(base_uv + disp_r + vec2(-1.0,  0.0) * scatter_radius, 0.002, 0.998)).r * 0.18;
    r += texture2D(texture0, clamp(base_uv + disp_r + vec2( 0.0,  1.0) * scatter_radius, 0.002, 0.998)).r * 0.18;
    r += texture2D(texture0, clamp(base_uv + disp_r + vec2( 0.0, -1.0) * scatter_radius, 0.002, 0.998)).r * 0.18;

    float g = texture2D(texture0, clamp(base_uv, 0.002, 0.998)).g * 0.28;
    g += texture2D(texture0, clamp(base_uv + vec2( 1.0,  0.0) * scatter_radius, 0.002, 0.998)).g * 0.18;
    g += texture2D(texture0, clamp(base_uv + vec2(-1.0,  0.0) * scatter_radius, 0.002, 0.998)).g * 0.18;
    g += texture2D(texture0, clamp(base_uv + vec2( 0.0,  1.0) * scatter_radius, 0.002, 0.998)).g * 0.18;
    g += texture2D(texture0, clamp(base_uv + vec2( 0.0, -1.0) * scatter_radius, 0.002, 0.998)).g * 0.18;

    float b = texture2D(texture0, clamp(base_uv + disp_b, 0.002, 0.998)).b * 0.28;
    b += texture2D(texture0, clamp(base_uv + disp_b + vec2( 1.0,  0.0) * scatter_radius, 0.002, 0.998)).b * 0.18;
    b += texture2D(texture0, clamp(base_uv + disp_b + vec2(-1.0,  0.0) * scatter_radius, 0.002, 0.998)).b * 0.18;
    b += texture2D(texture0, clamp(base_uv + disp_b + vec2( 0.0,  1.0) * scatter_radius, 0.002, 0.998)).b * 0.18;
    b += texture2D(texture0, clamp(base_uv + disp_b + vec2( 0.0, -1.0) * scatter_radius, 0.002, 0.998)).b * 0.18;

    vec3 col = vec3(r, g, b);

    // Uniform icy tinting across all facets (equal transmission)
    if (u_is_dark > 0.5) {
        col = mix(col, col * vec3(0.92, 0.96, 1.04) + vec3(0.06, 0.09, 0.14), 0.18);
    } else {
        col = mix(col, col * vec3(0.96, 0.98, 1.02) + vec3(0.09, 0.12, 0.16), 0.16);
    }

    // Surface frost tactile film ("шум" на поверхности)
    float frost_grain = (frost_noise - 0.5) * 0.08 + (fine_grain - 0.5) * 0.04;
    col += vec3(0.85, 0.94, 1.0) * frost_grain;

    // Specular lighting & sparkling glints on the frosted ice surface
    vec3 L = normalize(vec3(0.30, 0.85, 0.55));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 22.0) * 0.35;
    float sparkle = pow(max(dot(N, H), 0.0), 48.0) * 0.75 * smoothstep(0.42, 0.75, frost_noise);
    col += (vec3(0.90, 0.96, 1.0) * spec + vec3(1.0) * sparkle);

    // Capsule outer rim highlight (ice block chamfer)
    float edge_depth = max(-dist, 0.0);
    float rim = smoothstep(2.6, 0.6, edge_depth) * smoothstep(0.0, 0.6, edge_depth);
    float edge_aa = smoothstep(1.5, 0.0, abs(dist));
    col += vec3(0.85, 0.95, 1.0) * rim * 0.35;
    col = mix(col, vec3(1.0), edge_aa * 0.22);

    // Synchronized delicate icy shimmer
    float shimmer = sin(time * 0.7 + cell_id * 0.3) * 0.020;
    col += vec3(0.5, 0.8, 1.0) * max(shimmer, 0.0);

    gl_FragColor = vec4(col, alpha);
}
"""


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
        """Initializes RenderContext and background texture lazily when OpenGL context is ready."""
        if self._init_done:
            return True

        try:
            w = max(1, int(self.dockbar.width or dp(300)))
            h = max(1, int(self.dockbar.height or dp(78)))
            self.bg_texture = Texture.create(size=(w, h), colorfmt="rgba")

            rc = RenderContext(use_parent_projection=True, use_parent_modelview=True)
            rc.shader.vs = SHADER_VS
            self.callback = Callback(self._capture_framebuffer)
            rc.add(self.callback)
            with rc:
                self.rect = Rectangle(texture=self.bg_texture, pos=self.dockbar.pos, size=self.dockbar.size)
            self.render_context = rc
            # Insert at beginning of canvas.before so it draws behind dock items
            self.dockbar.canvas.before.insert(0, rc)
            self._init_done = True
            logger.info("DockbarShaderRenderer initialized RenderContext with framebuffer capture successfully")
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

            if self.bg_texture.size != (w, h):
                self.bg_texture = Texture.create(size=(w, h), colorfmt="rgba")
                if self.rect:
                    self.rect.texture = self.bg_texture

            self.bg_texture.bind()
            glCopyTexSubImage2D(
                GL_TEXTURE_2D, 0, 0, 0,
                max(0, win_x), max(0, win_y),
                min(w, int(Window.width)), min(h, int(Window.height))
            )
        except Exception as e:
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

        # Select fragment shader
        if self.current_bg_type == "liquid_glass":
            self.render_context.shader.fs = LIQUID_GLASS_FS
        elif self.current_bg_type == "glassy_ice":
            self.render_context.shader.fs = GLASSY_ICE_FS
        else:
            return

        if not self.render_context.shader.success:
            logger.error("Dockbar shader error: %s", self.render_context.shader.log)
            return

        # Start animation ticker if not already running
        if self._clock_event is None:
            self._clock_event = Clock.schedule_interval(self._on_tick, 1.0 / 30.0)

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

        pad_x = dp(16)
        pad_y = dp(10)
        if u_style == 0:  # impact
            cap_x = dockbar.x
            cap_y = dockbar.y
            cap_w = dockbar.width
            cap_h = dockbar.height
            radius = 0.0
        elif u_style == 1:  # telegram
            cap_x = dockbar.x + pad_x
            cap_y = dockbar.y + pad_y
            cap_w = max(1.0, dockbar.width - pad_x * 2)
            cap_h = max(1.0, dockbar.height - pad_y * 2)
            radius = float(cap_h / 2.0)
        elif u_style == 2:  # incy
            cap_x = dockbar.x + pad_x
            cap_y = dockbar.y + pad_y
            cap_w = max(1.0, dockbar.width - pad_x * 2)
            cap_h = max(1.0, dockbar.height - pad_y * 2)
            radius = float(dp(16))
        else:  # pinterest
            cap_x = dockbar.x
            cap_y = dockbar.y
            cap_w = dockbar.width
            cap_h = dockbar.height
            sel = getattr(app, "dockbar_selection", "squares")
            radius = float(dp(27) if sel == "circles" else dp(16))

        rc = self.render_context
        rc["u_style"] = int(u_style)
        rc["u_capsule"] = [float(cap_x), float(cap_y), float(cap_w), float(cap_h)]
        rc["u_radius"] = float(radius)

        btn_sz = float(dp(54))
        for i, item_id in enumerate(["item_dialogs", "item_logs", "item_settings"], 1):
            item = dockbar.ids.get(item_id) if hasattr(dockbar, "ids") else None
            if item:
                cx, cy = item.center_x, item.center_y
                rc[f"u_island{i}"] = [float(cx - btn_sz / 2.0), float(cy - btn_sz / 2.0), btn_sz, btn_sz]
            else:
                offset_x = dockbar.x + (dockbar.width / 4.0) * i
                rc[f"u_island{i}"] = [float(offset_x - btn_sz / 2.0), float(dockbar.center_y - btn_sz / 2.0), btn_sz, btn_sz]

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
