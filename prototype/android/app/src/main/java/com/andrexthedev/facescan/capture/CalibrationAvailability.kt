package com.andrexthedev.facescan.capture

/** Nur Vorhandensein statischer Metadaten; kein Nachweis von Kalibrierung oder Frame-Zuordnung. */
data class CalibrationAvailability(val intrinsics: State, val distortion: State, val activeArray: State) {
    enum class State(val label: String) { PRESENT("vorhanden"), MISSING("nicht gemeldet"), INVALID("ungültig"), UNKNOWN("nicht geprüft") }
    companion object {
        val UNKNOWN = CalibrationAvailability(State.UNKNOWN, State.UNKNOWN, State.UNKNOWN)
        fun classify(intrinsics: FloatArray?, distortion: FloatArray?, activeWidth: Int?, activeHeight: Int?): CalibrationAvailability {
            val intr = when {
                intrinsics == null -> State.MISSING
                intrinsics.size != 5 || intrinsics.any { !it.isFinite() } || intrinsics[0] <= 0 || intrinsics[1] <= 0 -> State.INVALID
                else -> State.PRESENT
            }
            val dist = when {
                distortion == null -> State.MISSING
                distortion.size != 5 || distortion.any { !it.isFinite() } -> State.INVALID
                else -> State.PRESENT
            }
            val rect = when {
                activeWidth == null || activeHeight == null -> State.MISSING
                activeWidth <= 0 || activeHeight <= 0 -> State.INVALID
                else -> State.PRESENT
            }
            return CalibrationAvailability(intr, dist, rect)
        }
    }
}
