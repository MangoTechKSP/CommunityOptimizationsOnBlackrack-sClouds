using System.Collections.Generic;
using UnityEngine;

namespace Utils;

/// <summary>
/// What a camera is doing, as far as the cloud pipeline is concerned.
/// </summary>
public enum CameraRole
{
	/// <summary>Not one of the cameras the stock game creates by name.</summary>
	Unknown,
	/// <summary>Near/far main pair, near half (stock name "Camera 00").</summary>
	MainNear,
	/// <summary>Near/far main pair, far half (stock name "Camera 01").</summary>
	MainFar,
	/// <summary>Scenery reflection camera used by the tracking-station dish and similar (stock name "TRReflectionCamera").</summary>
	SceneryReflection,
	/// <summary>Camera that renders reflection probes (stock name "Reflection Probes Camera").</summary>
	ReflectionProbe,
	/// <summary>Depth-only camera used by the ocean/atmosphere (stock name "DepthCamera").</summary>
	DepthOnly,
	/// <summary>Near-mirror camera used by the ocean (stock name "NearCamera").</summary>
	NearMirror,
}

/// <summary>
/// Opt-in marker that pins a camera's role explicitly. Attach it to a camera and the pipeline stops
/// guessing from the GameObject name, which is what stock KSP and the decompiled Scatterer code do.
/// Another mod that renames or re-parents a camera can attach one of these to keep the cloud
/// pipeline working, and a camera that the pipeline should ignore can be marked
/// <see cref="CameraRole.DepthOnly"/>.
/// </summary>
public sealed class CameraRoleMarker : MonoBehaviour
{
	public CameraRole role = CameraRole.Unknown;
}

/// <summary>
/// Single source of truth for "which camera is this?". Stock KSP identifies its cameras by
/// GameObject name, and several decompiled EVE/Scatterer classes do the same; the name comparisons
/// are repeated in a dozen places and each of them silently misses any camera a mod adds or renames.
///
/// Lookup order per camera:
/// <list type="number">
/// <item>a <see cref="CameraRoleMarker"/> component (explicit, survives renames);</item>
/// <item>the stock name table below;</item>
/// <item><see cref="CameraRole.Unknown"/>.</item>
/// </list>
///
/// Results are cached per camera instance and invalidated by a name change (or by calling
/// <see cref="ResetCache"/> after a scene load), because <c>Camera.name</c> is a native property
/// and reading it several times per frame in several classes showed up in the cloud pass.
/// </summary>
public static class CameraRoles
{
	/// <summary>Stock GameObject names, in the order they were hard-coded in the pipeline.</summary>
	private static readonly Dictionary<string, CameraRole> StockNames = new Dictionary<string, CameraRole>
	{
		{ "Camera 00", CameraRole.MainNear },
		{ "Camera 01", CameraRole.MainFar },
		{ "TRReflectionCamera", CameraRole.SceneryReflection },
		{ "Reflection Probes Camera", CameraRole.ReflectionProbe },
		{ "DepthCamera", CameraRole.DepthOnly },
		{ "NearCamera", CameraRole.NearMirror },
	};

	private struct Entry
	{
		public string name;

		public CameraRole role;
	}

	private static readonly Dictionary<int, Entry> cache = new Dictionary<int, Entry>();

	/// <summary>Role of the camera, from its marker component or its stock name.</summary>
	public static CameraRole GetRole(Camera camera)
	{
		if ((object)camera == null)
		{
			return CameraRole.Unknown;
		}
		int id = camera.GetInstanceID();
		if (cache.TryGetValue(id, out var cached))
		{
			// A redressed camera (renamed, or a marker added later) must not keep the old answer.
			if (cached.name == camera.name)
			{
				return cached.role;
			}
		}
		CameraRole role = Resolve(camera);
		cache[id] = new Entry
		{
			name = camera.name,
			role = role
		};
		return role;
	}

	public static void ResetCache()
	{
		cache.Clear();
	}

	private static CameraRole Resolve(Camera camera)
	{
		CameraRoleMarker marker = camera.GetComponent<CameraRoleMarker>();
		if (marker != null && (object)marker != null && marker.role != CameraRole.Unknown)
		{
			return marker.role;
		}
		if (StockNames.TryGetValue(camera.name, out var role))
		{
			return role;
		}
		return CameraRole.Unknown;
	}

	/// <summary>True for the two cameras that render a view of the world (near and far halves).</summary>
	public static bool IsMainCamera(Camera camera)
	{
		CameraRole role = GetRole(camera);
		return role == CameraRole.MainNear || role == CameraRole.MainFar;
	}

	/// <summary>True for both reflection cameras: the scenery one and the probe one.</summary>
	public static bool IsReflectionCamera(Camera camera)
	{
		CameraRole role = GetRole(camera);
		return role == CameraRole.SceneryReflection || role == CameraRole.ReflectionProbe;
	}

	/// <summary>True for cameras whose cloud output is thrown away (depth-only and the near mirror).</summary>
	public static bool IsSkippedCamera(Camera camera)
	{
		CameraRole role = GetRole(camera);
		return role == CameraRole.DepthOnly || role == CameraRole.NearMirror;
	}

	/// <summary>Reused buffer for <see cref="FindFirst"/>, so the lookup does not allocate per call.</summary>
	private static Camera[] cameraBuffer;

	/// <summary>
	/// First enabled camera with the given role, or null. Replaces the
	/// <c>Camera.allCameras.Where(c =&gt; GetRole(c) == role).FirstOrDefault()</c> pattern, which
	/// allocates a fresh array (Unity returns a copy) plus a LINQ iterator every call.
	/// </summary>
	public static Camera FindFirst(CameraRole role)
	{
		int count = Camera.allCamerasCount;
		if (count <= 0)
		{
			return null;
		}
		if (cameraBuffer == null || cameraBuffer.Length < count)
		{
			cameraBuffer = new Camera[count];
		}
		Camera.GetAllCameras(cameraBuffer);
		for (int i = 0; i < count; i++)
		{
			Camera candidate = cameraBuffer[i];
			if (candidate != null && GetRole(candidate) == role)
			{
				return candidate;
			}
		}
		return null;
	}
}
