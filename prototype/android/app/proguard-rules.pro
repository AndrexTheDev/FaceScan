# FaceScan – Release-Regeln
# Kein Logging im Release (es gibt auch kein Remote-Logging).
-assumenosideeffects class android.util.Log {
    public static int d(...);
    public static int v(...);
    public static int i(...);
}

# Modelle und Fixtures nicht verwuerfeln/verschieben lassen
-keep class com.andrexthedev.facescan.geometry.** { *; }
-keep class com.google.mediapipe.** { *; }
