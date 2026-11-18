package cloud.itonami.arbitrage

import android.content.res.Configuration
import android.os.Bundle
import android.view.View
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlin.math.max

// Android 15 draws apps edge to edge (targetSdk 35+) and the WebView reports no
// safe-area inset, so pad the content by the system bars, cutout and keyboard,
// and colour the bars to match the page (AWAI-3441, AWAI-3393; same form as
// awai-os apps/x402).
class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    val content = findViewById<View>(android.R.id.content)
    ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
      val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
      val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
      view.setPadding(bars.left, bars.top, bars.right, max(bars.bottom, ime.bottom))
      insets
    }
    applySystemBarAppearance(resources.configuration)
    ViewCompat.requestApplyInsets(content)
  }

  // uiMode is in the manifest's configChanges, so a theme switch arrives here
  // instead of recreating the activity.
  override fun onConfigurationChanged(newConfig: Configuration) {
    super.onConfigurationChanged(newConfig)
    applySystemBarAppearance(newConfig)
  }

  // The bars are drawn over the decor view, so set its colour to the page's
  // background (#f7f7f5 light / #121212 dark), with dark icons in light mode and
  // light icons in dark mode.
  private fun applySystemBarAppearance(config: Configuration) {
    val light = (config.uiMode and Configuration.UI_MODE_NIGHT_MASK) != Configuration.UI_MODE_NIGHT_YES
    window.decorView.setBackgroundColor(if (light) 0xFFF7F7F5.toInt() else 0xFF121212.toInt())
    // The 3-button navigation scrim does not follow a live theme switch; without
    // this the decor colour shows through it.
    if (android.os.Build.VERSION.SDK_INT >= 29) window.isNavigationBarContrastEnforced = false
    WindowInsetsControllerCompat(window, findViewById(android.R.id.content)).apply {
      isAppearanceLightStatusBars = light
      isAppearanceLightNavigationBars = light
    }
  }
}
