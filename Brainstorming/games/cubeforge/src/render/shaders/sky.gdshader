shader_type sky;

// CUBEFORGE sky.
//
// Everything is driven from GDScript (src/render/sky.gd): the time of day is
// never computed here, only the layers are. Composition order, back to front:
//   1. vertical gradient horizon -> zenith (plus a ground tint below)
//   2. warm scattering glow around the sun azimuth, hugging the horizon
//   3. sun disc with a soft rim and a wide halo
//   4. moon disc with a crescent carved by a second offset disc
//   5. star field, hashed from a quantised eye direction, night only
//   6. procedural clouds on a virtual plane, drifting and sun lit

// ---------------------------------------------------------------------------
// Vertical gradient
// ---------------------------------------------------------------------------

uniform vec3 zenith_color : source_color = vec3(0.17, 0.38, 0.76);
uniform vec3 horizon_color : source_color = vec3(0.66, 0.80, 0.94);
uniform vec3 ground_color : source_color = vec3(0.12, 0.13, 0.16);
/// Higher values squeeze the horizon band closer to the horizon.
uniform float gradient_falloff : hint_range(0.5, 8.0) = 3.0;

// ---------------------------------------------------------------------------
// Sun
// ---------------------------------------------------------------------------

/// Unit vector pointing from the viewer towards the sun.
uniform vec3 sun_direction = vec3(0.0, 0.6, 0.8);
uniform vec3 sun_disc_color : source_color = vec3(1.0, 0.96, 0.88);
uniform vec3 sun_glow_color : source_color = vec3(1.0, 0.46, 0.18);
uniform float sun_disc_size : hint_range(0.005, 0.20) = 0.031;
uniform float sun_disc_edge : hint_range(0.0005, 0.06) = 0.008;
uniform float sun_halo_strength : hint_range(0.0, 4.0) = 0.40;
uniform float sun_halo_tightness : hint_range(1.0, 60.0) = 7.0;
/// 0 hides the disc completely (sun below the horizon).
uniform float sun_visibility : hint_range(0.0, 1.0) = 1.0;

/// Warm band around the sun azimuth, the sunrise and sunset signature.
uniform float horizon_glow_strength : hint_range(0.0, 4.0) = 0.25;
uniform float horizon_glow_tightness : hint_range(1.0, 24.0) = 5.5;
uniform float horizon_glow_focus : hint_range(1.0, 16.0) = 3.5;

// ---------------------------------------------------------------------------
// Moon
// ---------------------------------------------------------------------------

uniform vec3 moon_direction = vec3(0.0, -0.6, -0.8);
uniform vec3 moon_color : source_color = vec3(0.86, 0.90, 1.0);
uniform float moon_size : hint_range(0.005, 0.20) = 0.052;
/// 0 fully carved (new moon), 1 barely carved (nearly full).
uniform float moon_phase : hint_range(0.0, 1.4) = 0.8;
uniform float moon_halo_strength : hint_range(0.0, 2.0) = 0.22;
uniform float moon_halo_tightness : hint_range(1.0, 80.0) = 26.0;
uniform float moon_visibility : hint_range(0.0, 1.0) = 0.0;

// ---------------------------------------------------------------------------
// Stars
// ---------------------------------------------------------------------------

uniform vec3 star_color : source_color = vec3(0.92, 0.95, 1.0);
/// Cells per unit of direction. Bigger means smaller and denser stars.
uniform float star_density : hint_range(20.0, 400.0) = 96.0;
/// Fraction of cells that hold no star at all.
uniform float star_sparsity : hint_range(0.0, 0.999) = 0.93;
/// Star radius in cell units, kept well below 0.5 to avoid cell clipping.
uniform float star_size : hint_range(0.02, 0.45) = 0.21;
uniform float star_twinkle_speed : hint_range(0.0, 6.0) = 0.7;
/// 0 by day, 1 in the middle of the night.
uniform float star_intensity : hint_range(0.0, 4.0) = 0.0;

// ---------------------------------------------------------------------------
// Clouds
// ---------------------------------------------------------------------------

uniform vec3 cloud_light_color : source_color = vec3(1.0, 0.99, 0.97);
uniform vec3 cloud_shadow_color : source_color = vec3(0.44, 0.50, 0.60);
uniform float cloud_scale : hint_range(0.05, 6.0) = 0.55;
uniform float cloud_speed : hint_range(0.0, 1.0) = 0.016;
/// Noise threshold. Higher means fewer clouds.
uniform float cloud_coverage : hint_range(0.0, 1.2) = 0.52;
uniform float cloud_softness : hint_range(0.01, 0.8) = 0.24;
uniform float cloud_opacity : hint_range(0.0, 1.0) = 0.85;
/// Distance of the self shadowing sample, taken towards the sun azimuth.
uniform float cloud_shade_step : hint_range(0.0, 4.0) = 0.55;
uniform float cloud_shade_gain : hint_range(0.0, 8.0) = 2.6;
uniform float cloud_rim_glow : hint_range(0.0, 3.0) = 0.35;
/// Elevation where clouds start to appear. Hides the projection singularity.
uniform float cloud_horizon_fade : hint_range(0.0, 0.5) = 0.055;

// ---------------------------------------------------------------------------
// Hashes and noise
// ---------------------------------------------------------------------------

float hash12(vec2 p) {
	vec3 q = fract(vec3(p.x, p.y, p.x) * vec3(0.1031, 0.1030, 0.0973));
	q += vec3(dot(q, vec3(q.y, q.z, q.x) + vec3(33.33)));
	return fract((q.x + q.y) * q.z);
}

float hash13(vec3 p) {
	vec3 q = fract(p * vec3(0.1031, 0.1030, 0.0973));
	q += vec3(dot(q, vec3(q.z, q.y, q.x) + vec3(31.32)));
	return fract((q.x + q.y) * q.z);
}

float value_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = p - i;
	vec2 w = f * f * (vec2(3.0) - 2.0 * f);
	float a = hash12(i);
	float b = hash12(i + vec2(1.0, 0.0));
	float c = hash12(i + vec2(0.0, 1.0));
	float d = hash12(i + vec2(1.0, 1.0));
	return mix(mix(a, b, w.x), mix(c, d, w.x), w.y);
}

/// Three octaves of value noise, roughly normalised to 0..1.
float cloud_fbm(vec2 p) {
	float sum = 0.0;
	float amp = 0.62;
	vec2 q = p;
	for (int i = 0; i < 3; i++) {
		sum += amp * value_noise(q);
		q = q * 2.07 + vec2(19.3, 7.7);
		amp *= 0.48;
	}
	return sum;
}

// ---------------------------------------------------------------------------
// Stars
// ---------------------------------------------------------------------------

/// One candidate star per cell of the quantised direction. The jittered
/// position is clamped so a star never crosses its own cell border, which
/// keeps the field stable while the camera turns.
float star_field(vec3 dir, float t) {
	float above = smoothstep(-0.02, 0.16, dir.y);
	if (above <= 0.0) {
		return 0.0;
	}
	vec3 p = dir * star_density;
	vec3 cell = floor(p);
	vec3 f = p - cell;
	float pick = hash13(cell + vec3(0.5));
	if (pick < star_sparsity) {
		return 0.0;
	}
	float mag = (pick - star_sparsity) / max(1.0 - star_sparsity, 0.001);
	vec3 jitter = vec3(
		hash13(cell + vec3(13.7)),
		hash13(cell + vec3(27.1)),
		hash13(cell + vec3(41.9)));
	jitter = clamp(jitter, vec3(star_size), vec3(1.0 - star_size));
	float d = length(f - jitter);
	float core = 1.0 - smoothstep(star_size * 0.30, star_size, d);
	float twinkle = 0.62 + 0.38 * sin(t * star_twinkle_speed + pick * 47.0);
	return core * mix(0.22, 1.0, mag * mag) * twinkle * above;
}

// ---------------------------------------------------------------------------
// Composition
// ---------------------------------------------------------------------------

void sky() {
	vec3 dir = normalize(EYEDIR);
	float ey = dir.y;

	// 1. base gradient.
	float t_hor = pow(1.0 - clamp(ey, 0.0, 1.0), gradient_falloff);
	vec3 col = mix(zenith_color, horizon_color, t_hor);
	col = mix(col, ground_color, smoothstep(0.0, -0.20, ey));

	vec3 sun_dir = normalize(sun_direction);
	vec3 moon_dir = normalize(moon_direction);

	// Azimuth only versions, used by the horizon glow and the cloud shading.
	vec3 sun_flat = vec3(sun_dir.x, 0.0, sun_dir.z);
	sun_flat = sun_flat / max(length(sun_flat), 0.0001);
	vec3 eye_flat = vec3(dir.x, 0.0, dir.z);
	eye_flat = eye_flat / max(length(eye_flat), 0.0001);

	// 2. warm scattering around the sun azimuth, concentrated at the horizon.
	float azimuth = max(dot(sun_flat, eye_flat), 0.0);
	float band = exp(-abs(ey) * horizon_glow_tightness);
	col += sun_glow_color * (pow(azimuth, horizon_glow_focus) * band * horizon_glow_strength);

	// 3. sun disc, soft rim and wide halo.
	float sun_a = length(dir - sun_dir);
	float disc = 1.0 - smoothstep(sun_disc_size, sun_disc_size + sun_disc_edge, sun_a);
	float rim = 1.0 - smoothstep(sun_disc_size, sun_disc_size * 3.0 + sun_disc_edge, sun_a);
	float halo = exp(-sun_a * sun_halo_tightness) * sun_halo_strength;
	col += sun_disc_color * ((disc * 7.0 + rim * 0.45 + halo) * sun_visibility);

	// 4. moon, a disc minus a second disc offset along its own tangent.
	vec3 ref_up = abs(moon_dir.y) > 0.99 ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);
	vec3 tangent = normalize(cross(moon_dir, ref_up));
	vec3 carve_dir = normalize(moon_dir
		+ tangent * (moon_size * moon_phase * 2.0)
		+ ref_up * (moon_size * moon_phase * 0.40));
	float moon_a = length(dir - moon_dir);
	float moon_b = length(dir - carve_dir);
	// The carving disc is slightly larger than the moon, which gives the crescent
	// thin pointed cusps instead of a round bite.
	float carve_size = moon_size * 1.12;
	float moon_disc = 1.0 - smoothstep(moon_size * 0.84, moon_size, moon_a);
	float moon_cut = 1.0 - smoothstep(carve_size * 0.86, carve_size, moon_b);
	float moon_body = clamp(moon_disc - moon_cut, 0.0, 1.0);
	float moon_glow = exp(-moon_a * moon_halo_tightness) * moon_halo_strength;
	col += moon_color * ((moon_body * 3.2 + moon_glow) * moon_visibility);

	// 5. stars, invisible by day because star_intensity is zero then.
	if (star_intensity > 0.001) {
		col += star_color * (star_field(dir, TIME) * star_intensity);
	}

	// 6. clouds on a virtual plane. The denominator is clamped well above zero
	// so the projection never explodes into aliasing near the horizon.
	float cloud_fade = smoothstep(cloud_horizon_fade, cloud_horizon_fade + 0.26, ey);
	if (cloud_fade > 0.001 && cloud_opacity > 0.001) {
		vec2 plane = vec2(dir.x, dir.z) / max(ey, 0.10) * cloud_scale;
		vec2 drift = vec2(TIME * cloud_speed, TIME * cloud_speed * 0.42);
		float n_here = cloud_fbm(plane + drift);
		vec2 towards_sun = vec2(sun_flat.x, sun_flat.z) * cloud_shade_step;
		float n_sun = cloud_fbm(plane + drift - towards_sun);
		float density = smoothstep(cloud_coverage, cloud_coverage + cloud_softness, n_here);
		density *= cloud_fade * cloud_opacity;
		float lit = clamp((n_here - n_sun) * cloud_shade_gain + 0.5, 0.0, 1.0);
		float sun_side = pow(max(dot(dir, sun_dir), 0.0), 3.0);
		vec3 cc = mix(cloud_shadow_color, cloud_light_color,
			clamp(lit * 0.75 + sun_side * 0.45, 0.0, 1.0));
		cc += sun_glow_color * (sun_side * cloud_rim_glow * sun_visibility);
		col = mix(col, cc, clamp(density, 0.0, 1.0));
	}

	COLOR = col;
}
