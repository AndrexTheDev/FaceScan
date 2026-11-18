package com.andrexthedev.facescan.diagnostics

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.provider.Settings

/** Best-effort Systemzustand, keine Netzwerkmessung oder Überwachungs-App. */
object NetworkState {
    fun airplaneWithoutInternetNetwork(context: Context): Boolean = try {
        val airplane = Settings.Global.getInt(context.contentResolver, Settings.Global.AIRPLANE_MODE_ON, 0) == 1
        val connectivity = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val internetCapable = connectivity.allNetworks.any { network ->
            connectivity.getNetworkCapabilities(network)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
        }
        airplane && !internetCapable
    } catch (_: Exception) { false }
}
