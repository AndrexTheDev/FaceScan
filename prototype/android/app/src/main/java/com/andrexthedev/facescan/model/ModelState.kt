package com.andrexthedev.facescan.model

import java.io.File

sealed interface ModelState {
    data object Loading : ModelState
    data class Ready(val file: File) : ModelState
    data object Failed : ModelState
}
