using UnityEditor;
using UnityEngine;
using System.IO;

// Builds GameData/EnvironmentalVisualEnhancements/eveshaders_tweak.bundle.
// Menu: EVE/Build tweak bundle      Batch: -executeMethod TweakBundleBuilder.CIBuild
public static class TweakBundleBuilder
{
    const string BundleName = "eveshaders_tweak.bundle";
    const string AssetDir = "Assets/Shaders";
    const string OutputDir = "BuildOut";

    [MenuItem("EVE/Build tweak bundle")]
    public static void BuildMenu()
    {
        Build();
        EditorUtility.DisplayDialog("EVE tweak bundle", "Built into " + Path.GetFullPath(OutputDir), "OK");
    }

    public static void CIBuild()
    {
        try
        {
            Build();
            Debug.Log("[EVE-TWEAK] BUILD OK");
            EditorApplication.Exit(0);
        }
        catch (System.Exception e)
        {
            Debug.LogError("[EVE-TWEAK] BUILD FAILED: " + e);
            EditorApplication.Exit(1);
        }
    }

    static void Build()
    {
        // Every shader in Assets/Shaders goes into the one override bundle.
        foreach (string guid in AssetDatabase.FindAssets("t:Shader", new[] { AssetDir }))
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            AssetImporter importer = AssetImporter.GetAtPath(path);
            importer.assetBundleName = BundleName;
            importer.SaveAndReimport();
            Debug.Log("[EVE-TWEAK] packed " + path + " -> " + BundleName);
        }

        Directory.CreateDirectory(OutputDir);
        BuildPipeline.BuildAssetBundles(
            OutputDir,
            BuildAssetBundleOptions.ChunkBasedCompression,
            BuildTarget.StandaloneWindows64);
    }
}
