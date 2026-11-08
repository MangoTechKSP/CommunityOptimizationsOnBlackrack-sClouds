using System;
using KSP.UI.Screens;
using ShaderLoader;
using UnityEngine;

namespace Atmosphere;

/// <summary>
/// A second AppLauncher button, next to EVE's own, that opens a compact panel for the raymarched
/// volumetric clouds only: the three knobs this fork added, live values pulled from the renderer's
/// diagnostics, and the current reprojection/light-volume state.
///
/// Why a separate entry point: reaching `edgeWisp`/`shadowCasterStrength` through the stock EVE
/// window takes Alt+0, then a manager selector, then the config-file selector, then the object
/// selector (three nested lists) — and the values are only re-read on a preset switch. This panel is
/// one click, applies on release, and shows the numbers the log line prints so a change can be
/// judged without opening KSP.log.
///
/// It is a tuning aid, not a second settings system: the preset file stays the source of truth, and
/// "Reload preset" throws away all live tweaks.
/// </summary>
[KSPAddon(KSPAddon.Startup.EveryScene, false)]
public class VolumetricCloudsWindow : MonoBehaviour
{
	private const int WindowId = 33026;

	private const float WindowWidth = 360f;

	private const float WindowHeight = 400f;

	private static ApplicationLauncherButton button;

	private static Texture2D buttonTexture;

	private static bool windowOpen;

	private static bool subscribed;

	private Rect windowRect = new Rect(40f, 120f, WindowWidth, WindowHeight);

	/// <summary>
	/// Live slider state. Seeded from the manager on open and written back on mouse-up; kept here so
	/// dragging does not fight with the manager's clamping while the thumb moves.
	/// </summary>
	private static float wispSlider = -1f;

	private static float shadowSlider = -1f;

	private static float upsampleSlider = -1f;

	private static float multipleScatterSlider = -1f;

	private static float bounceSlider = -1f;

	private static float groundShadowSlider = -1f;

	private static float haloSlider = -1f;

	private static float rainbowSlider = -1f;

	private static float erosionSlider = -1f;

	private static float baseDarknessSlider = -1f;

	private static float breakupSlider = -1f;

	private static float sculptSlider = -1f;
	private static float edgeGlowSlider = -1f;
	private static float contourSlider = -1f;
	private static float detailFrequencySlider = -1f;
	private static float contourThresholdSlider = -1f;
	private static float contourBandSlider = -1f;

	private static bool dirty;

	/// <summary>Scroll state, so the status block plus three sliders always fit the window.</summary>
	private static Vector2 scroll;

	/// <summary>
	/// True when the shader bundle is loaded, i.e. when the volumetric path can render at all. Used
	/// only to explain an empty status line, never to hide the panel.
	/// </summary>
	private static bool ShadersLoaded => ShaderLoaderClass.loaded;

	private void Awake()
	{
		GameEvents.onGUIApplicationLauncherReady.Add(AddButton);
		GameEvents.onGUIApplicationLauncherUnreadifying.Add(RemoveButton);
		subscribed = true;
		// the launcher may already be up when this addon starts (main menu -> flight is not the
		// first scene), in which case onGUIApplicationLauncherReady will never fire again
		if (ApplicationLauncher.Instance != null)
		{
			AddButton();
		}
	}

	private void OnDestroy()
	{
		if (subscribed)
		{
			GameEvents.onGUIApplicationLauncherReady.Remove(AddButton);
			GameEvents.onGUIApplicationLauncherUnreadifying.Remove(RemoveButton);
			subscribed = false;
		}
		RemoveButton(HighLogic.LoadedScene);
	}

	private void AddButton()
	{
		if ((UnityEngine.Object)(object)button != (UnityEngine.Object)null)
		{
			return;
		}
		ApplicationLauncher launcher = ApplicationLauncher.Instance;
		if (launcher == null)
		{
			return;
		}
		button = launcher.AddModApplication(OpenPanel, ClosePanel, null, null, null, null, ApplicationLauncher.AppScenes.SPACECENTER | ApplicationLauncher.AppScenes.FLIGHT | ApplicationLauncher.AppScenes.TRACKSTATION, GetButtonTexture());
	}

	private void RemoveButton(GameScenes data)
	{
		if ((UnityEngine.Object)(object)button != (UnityEngine.Object)null)
		{
			ApplicationLauncher launcher = ApplicationLauncher.Instance;
			if (launcher != null)
			{
				launcher.RemoveModApplication(button);
			}
			button = null;
		}
		windowOpen = false;
	}

	private static Texture2D GetButtonTexture()
	{
		if ((UnityEngine.Object)(object)buttonTexture != (UnityEngine.Object)null)
		{
			return buttonTexture;
		}
		// A generated icon on purpose: EVE's own button uses
		// EnvironmentalVisualEnhancements/button, and two identical toolbar buttons would be
		// indistinguishable. Drawing it here also keeps the panel from depending on a shipped asset
		// (a missing texture would register a button users cannot find). Three soft blobs over a
		// dusky sky — a cloud glyph at toolbar size.
		buttonTexture = new Texture2D(38, 38, TextureFormat.RGBA32, false);
		Color[] pixels = new Color[38 * 38];
		for (int y = 0; y < 38; y++)
		{
			for (int x = 0; x < 38; x++)
			{
				float t = y / 37f;
				Color sky = Color.Lerp(new Color(0.12f, 0.16f, 0.26f), new Color(0.32f, 0.42f, 0.58f), t);
				float cloud = 0f;
				cloud = Mathf.Max(cloud, Blob(x, y, 13f, 21f, 8.5f));
				cloud = Mathf.Max(cloud, Blob(x, y, 21f, 18.5f, 11f));
				cloud = Mathf.Max(cloud, Blob(x, y, 27.5f, 22f, 7.5f));
				Color cloudColor = new Color(0.93f, 0.95f, 0.98f, 1f);
				pixels[y * 38 + x] = Color.Lerp(sky, cloudColor, Mathf.Clamp01(cloud));
			}
		}
		buttonTexture.SetPixels(pixels);
		buttonTexture.Apply();
		return buttonTexture;
	}

	/// <summary>Soft-edged disc, 0 outside the radius and 1 at the centre (2 px feather).</summary>
	private static float Blob(float x, float y, float centerX, float centerY, float radius)
	{
		float dx = x - centerX;
		float dy = y - centerY;
		float distance = Mathf.Sqrt(dx * dx + dy * dy);
		return Mathf.Clamp01((radius - distance) / 2f);
	}

	private void OpenPanel()
	{
		windowOpen = true;
		SeedSliders();
	}

	private void ClosePanel()
	{
		windowOpen = false;
		ApplyIfDirty();
	}

	private static void SeedSliders()
	{
		wispSlider = RaymarchedCloudsQualityManager.EdgeWisp;
		shadowSlider = RaymarchedCloudsQualityManager.ShadowCasterStrength;
		upsampleSlider = RaymarchedCloudsQualityManager.DepthUpsampleThreshold;
		multipleScatterSlider = RaymarchedCloudsQualityManager.MultipleScattering;
		bounceSlider = RaymarchedCloudsQualityManager.GroundBounce;
		groundShadowSlider = RaymarchedCloudsQualityManager.CloudShadowStrength;
		haloSlider = RaymarchedCloudsQualityManager.SkyHaloStrength;
		rainbowSlider = RaymarchedCloudsQualityManager.SkyRainbowStrength;
		erosionSlider = RaymarchedCloudsQualityManager.DetailErosionScale;
		baseDarknessSlider = RaymarchedCloudsQualityManager.BaseDarkness;
		breakupSlider = RaymarchedCloudsQualityManager.MacroBreakup;
		sculptSlider = RaymarchedCloudsQualityManager.SculptStrength;
		edgeGlowSlider = RaymarchedCloudsQualityManager.EdgeGlow;
		contourSlider = RaymarchedCloudsQualityManager.ContourHardness;
		detailFrequencySlider = RaymarchedCloudsQualityManager.DetailFrequency;
		contourThresholdSlider = RaymarchedCloudsQualityManager.ContourThreshold;
		contourBandSlider = RaymarchedCloudsQualityManager.ContourBand;
		dirty = false;
	}

	private void ApplyIfDirty()
	{
		if (!dirty)
		{
			return;
		}
		dirty = false;
		RaymarchedCloudsQualityManager.ApplyRuntimeOverrides(wispSlider, shadowSlider, upsampleSlider,
			multipleScatterSlider, bounceSlider, groundShadowSlider, haloSlider, rainbowSlider,
			erosionSlider, baseDarknessSlider, breakupSlider, sculptSlider, edgeGlowSlider, contourSlider,
			detailFrequencySlider, contourThresholdSlider, contourBandSlider);
	}

	private void OnGUI()
	{
		if (!windowOpen)
		{
			return;
		}
		if (wispSlider < 0f)
		{
			SeedSliders();
		}
		windowRect.width = WindowWidth;
		windowRect.height = WindowHeight;
		windowRect = GUI.Window(WindowId, windowRect, DrawWindow, "Volumetric Clouds");
		// keep the title bar reachable: a window dragged past an edge (or left there across a
		// resolution change) would otherwise be impossible to grab again
		windowRect.x = Mathf.Clamp(windowRect.x, 0f - WindowWidth + 60f, Screen.width - 60f);
		windowRect.y = Mathf.Clamp(windowRect.y, 0f, Screen.height - 30f);
	}

	private void DrawWindow(int id)
	{
		GUILayout.BeginVertical();
		scroll = GUILayout.BeginScrollView(scroll);
		DrawStatus();
		GUILayout.Space(6f);
		DrawSlider("Edge wisps", ref wispSlider, 0f, 1f, "0 = ported blob edges, 0.35 = shipped, >=0.5 costs a third curl fetch");
		DrawSlider("Cloud-on-cloud shadows", ref shadowSlider, 0f, 1f, "0 = off, 0.5 = shipped; only the direct term is attenuated");
		DrawSlider("Depth upsampler tolerance", ref upsampleSlider, 0.01f, 2f, "0.1 = shipped; lower sharpens edges, higher smears them");
		GUILayout.Space(4f);
		GUILayout.Label("Lighting", BoldStyle());
		DrawSlider("Multiple scattering", ref multipleScatterSlider, 0f, 1f, "0 = single scattering only (dark interiors), 0.4 = shipped; no extra texture fetches");
		DrawSlider("Ground bounce", ref bounceSlider, 0f, 1f, "Light reflected off sunlit ground into the cloud base; 0.25 = shipped, 0 = off");
		GUILayout.Space(4f);
		GUILayout.Label("Shadows and sky", BoldStyle());
		DrawSlider("Ground shadow", ref groundShadowSlider, 0f, 1f, "Cloud shadows on the terrain; 0.6 = shipped, 0 = off (removes the pass)");
		DrawSlider("Ice halo", ref haloSlider, 0f, 1f, "22 degree ring around the sun; 0.3 = shipped, 0 = off");
		DrawSlider("Rainbow", ref rainbowSlider, 0f, 1f, "Primary + secondary bow near the antisolar point; 0.35 = shipped, 0 = off");
		GUILayout.Space(4f);
		GUILayout.Label("Vertical structure", BoldStyle());
		DrawSlider("Detail erosion", ref erosionSlider, 0.5f, 4f, "How hard the detail noise eats the layer; 1 = stock, 1.45 = shipped, 2-3 = crisper cauliflower top");
		DrawSlider("Base darkness", ref baseDarknessSlider, 0f, 0.8f, "Light penetration from the top: darker undersides on thick decks; 0.22 = shipped");
		DrawSlider("Coverage breakup", ref breakupSlider, 0f, 1f, "Large-scale thinning of a fully covered layer; 0 = stock, 0.3 = shipped");
		DrawSlider("Sculpted shading", ref sculptSlider, 0f, 1f, "Density-gradient normals: bumps the sun term so a flat sheet still reads as a volume; 0.7 = shipped");
		DrawSlider("Edge glow", ref edgeGlowSlider, 0f, 2f, "Silver lining: lifts a thinning fringe instead of letting it go dark; 0.8 = shipped, 0 = off");
		DrawSlider("Contour hardness", ref contourSlider, 1f, 6f, "Steepens the cloud/sky transition so the outline is carved; 1 = ported curve, 2.6 = shipped");
		DrawSlider("Detail frequency", ref detailFrequencySlider, 0.5f, 8f, "Makes the detail erosion eat smaller puffs; 1 = ported tiling, 3 = shipped");
		DrawSlider("Contour threshold", ref contourThresholdSlider, 0f, 0.9f, "Coverage below this is thrown away as fringe; 0.35 = shipped, 0 = the 1.2.2 curve");
		DrawSlider("Contour band", ref contourBandSlider, 0.02f, 0.6f, "Width of the remaining transition; 0.18 = ~2 px, lower is a cut-out");
		// Apply once per drag, when the mouse is released anywhere in the window: reinitialising the
		// renderers while the thumb moves would rebuild render targets every frame. Applying on any
		// MouseUp (rather than only on a slider's own release event) also covers the case where the
		// thumb is released outside the slider after dragging past its end.
		if (dirty && Event.current != null && Event.current.type == EventType.MouseUp)
		{
			ApplyIfDirty();
		}
		GUILayout.Space(6f);
		GUILayout.BeginHorizontal();
		if (GUILayout.Button("Apply now", GUILayout.Height(24f)))
		{
			ApplyIfDirty();
		}
		bool wasEnabled = GUI.enabled;
		GUI.enabled = dirty;
		if (GUILayout.Button("Discard", GUILayout.Height(24f)))
		{
			SeedSliders();
		}
		GUI.enabled = wasEnabled;
		if (GUILayout.Button("Reload preset", GUILayout.Height(24f)))
		{
			RaymarchedCloudsQualityManager.ReloadActivePreset();
			SeedSliders();
		}
		GUILayout.EndHorizontal();
		GUILayout.Space(2f);
		GUILayout.Label("Live values override the active preset until the next scene load; the preset file stays the source of truth.", SmallStyle());
		GUILayout.EndScrollView();
		GUILayout.EndVertical();
		GUI.DragWindow(new Rect(0f, 0f, 10000f, 20f));
	}

	private static void DrawStatus()
	{
		string body = DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsBody;
		int volumes = DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsVolumes;
		GUILayout.Label("Status", BoldStyle());
		if (!ShadersLoaded)
		{
			GUILayout.Label("Shader bundle not loaded yet — the volumetric path cannot render.", SmallStyle());
			return;
		}
		if (volumes <= 0)
		{
			// Same four causes the diagnostic doc lists; the panel is where a user looks first, so
			// name them rather than printing "volumes=0" and leaving the reader to find docs.
			GUILayout.Label("No cloud volumes for this camera. Check: camera is a main flight camera, a\nquality preset is active, the layer is within load distance, and only the\nnearest clouded body is drawn.", SmallStyle());
			return;
		}
		GUILayout.Label($"body: {body}   layers: {volumes}   intervals: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsIntervals}", SmallStyle());
		GUILayout.Label($"reprojection: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsReprojectionX}x{DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsReprojectionY}   light volume: {(DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsLightVolume ? "on" : "off")}", SmallStyle());
		GUILayout.Label($"layers culled: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsCulled}   other body: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsOtherBody}", SmallStyle());
		GUILayout.Label($"cloud slices baked: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsDirectSlices}/{DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsVolumeSlices}", SmallStyle());
		string gpu = DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsGpuMs;
		GUILayout.Label($"cpu: {DeferredRaymarchedVolumetricCloudsRenderer.LastDiagnosticsCpuMs:0.00} ms/frame   gpu: {(gpu == "n/a" ? "n/a (frame timing stats off)" : gpu + " ms")}", SmallStyle());
	}

	/// <summary>
	/// One labelled slider. Only marks the batch dirty: the caller applies on mouse-up, on "Apply
	/// now" and on window close, so dragging never reinitialises the renderers.
	/// </summary>
	private static void DrawSlider(string label, ref float value, float min, float max, string tooltip)
	{
		GUILayout.BeginHorizontal();
		GUILayout.Label(label, GUILayout.Width(180f));
		GUILayout.Label(value.ToString("0.00"), GUILayout.Width(42f));
		float next = GUILayout.HorizontalSlider(value, min, max);
		GUILayout.EndHorizontal();
		if (!Mathf.Approximately(next, value))
		{
			value = next;
			dirty = true;
		}
		GUILayout.Label(tooltip, SmallStyle());
	}

	private static GUIStyle smallStyle;

	private static GUIStyle boldStyle;

	private static GUIStyle SmallStyle()
	{
		if (smallStyle == null)
		{
			smallStyle = new GUIStyle(GUI.skin.label)
			{
				fontSize = 11,
				wordWrap = true
			};
		}
		return smallStyle;
	}

	private static GUIStyle BoldStyle()
	{
		if (boldStyle == null)
		{
			boldStyle = new GUIStyle(GUI.skin.label)
			{
				fontStyle = FontStyle.Bold
			};
		}
		return boldStyle;
	}
}
