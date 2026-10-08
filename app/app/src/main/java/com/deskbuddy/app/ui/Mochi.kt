package com.deskbuddy.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

val MOODS = listOf(
    "default", "happy", "love", "star", "wink", "dizzy", "angry", "sad",
    "sleepy", "surprised", "smug", "nervous", "cat", "sleeping", "cute"
)

/*
 * Mochi's face — the same design as the firmware (src/face.cpp), drawn in
 * OLED pixel coordinates (128 x 64) and scaled to the composable.
 * [mood] is the expression, [face] the device state (listen/think/speak/notify/sleep).
 */

private enum class Shape { EYE, HEART, STAR, SPIRAL, CLOSED_HAPPY, CLOSED_SLEEP }
private enum class Mouth { NONE, SMALL, SMILE, GRIN, FROWN, O, TINY_O, WAVY, SMIRK, CAT, TALK }

private data class EyeP(
    val w: Float = 36f, val h: Float = 36f, val dy: Float = 0f, val r: Float = 10f,
    val lidIn: Float = 0f, val lidOut: Float = 0f, val pupR: Float = 7f,
    val pupDX: Float = 0f, val pupDY: Float = 0f,
)

private data class Look(
    val l: EyeP = EyeP(), val r: EyeP = EyeP(),
    val shapeL: Shape = Shape.EYE, val shapeR: Shape = Shape.EYE,
    val mouth: Mouth = Mouth.SMALL, val slit: Boolean = false,
)

private const val EYE_CY = 27f
private const val EYE_LX = 38f
private const val EYE_RX = 90f
private const val MOUTH_Y = 55f

private fun lookFor(mood: String, face: String): Look {
    fun both(e: EyeP, mouth: Mouth) = Look(e, e, mouth = mouth)
    when (face) {
        "listen" -> return both(EyeP(38f, 40f, r = 11f, pupR = 6f, pupDY = -5f), Mouth.NONE)
        "think" -> return both(EyeP(pupR = 6f), Mouth.SMIRK)
        "speak" -> return both(EyeP(), Mouth.TALK)
        "notify" -> return both(EyeP(36f, 42f, dy = -2f, r = 12f, pupR = 5f), Mouth.O)
    }
    val m = if (face == "sleep") "sleeping" else mood
    return when (m) {
        "happy" -> Look(shapeL = Shape.CLOSED_HAPPY, shapeR = Shape.CLOSED_HAPPY, mouth = Mouth.GRIN)
        "love" -> Look(shapeL = Shape.HEART, shapeR = Shape.HEART, mouth = Mouth.SMILE)
        "star" -> Look(shapeL = Shape.STAR, shapeR = Shape.STAR, mouth = Mouth.GRIN)
        "wink" -> Look(r = EyeP(pupDX = -2f), shapeL = Shape.CLOSED_HAPPY, mouth = Mouth.SMIRK)
        "dizzy" -> Look(shapeL = Shape.SPIRAL, shapeR = Shape.SPIRAL, mouth = Mouth.WAVY)
        "angry" -> both(EyeP(36f, 32f, dy = 2f, r = 8f, lidIn = 0.55f, pupR = 6f, pupDY = 4f), Mouth.FROWN)
        "sad" -> both(EyeP(34f, 32f, dy = 3f, lidIn = 0.05f, lidOut = 0.5f, pupR = 6f, pupDY = 5f), Mouth.FROWN)
        "sleepy" -> both(EyeP(36f, 34f, lidIn = 0.55f, lidOut = 0.55f, pupR = 6f, pupDY = 6f), Mouth.TINY_O)
        "surprised" -> both(EyeP(34f, 42f, dy = -2f, r = 13f, pupR = 5f), Mouth.O)
        "smug" -> both(EyeP(36f, 34f, lidIn = 0.42f, lidOut = 0.42f, pupR = 6f, pupDX = 7f, pupDY = 3f), Mouth.SMIRK)
        "nervous" -> both(EyeP(30f, 30f, dy = -1f, r = 9f, pupR = 5f), Mouth.WAVY)
        "cat" -> Look(EyeP(r = 18f, pupR = 0f), EyeP(r = 18f, pupR = 0f), mouth = Mouth.CAT, slit = true)
        "sleeping" -> Look(shapeL = Shape.CLOSED_SLEEP, shapeR = Shape.CLOSED_SLEEP, mouth = Mouth.NONE)
        "cute" -> both(EyeP(40f, 40f, r = 18f, pupR = 11f), Mouth.CAT)
        else -> Look()
    }
}

@Composable
fun MochiFace(mood: String, face: String = "idle", modifier: Modifier = Modifier, animate: Boolean = true) {
    val c = LocalPal.current
    val time by produceState(0L, animate) {
        if (animate) while (true) withFrameMillis { value = it }
    }
    Canvas(
        modifier
            .background(c.scr)
            .semantics { contentDescription = "Mochi looks $mood" }
    ) {
        scale(size.width / 128f, size.height / 64f, pivot = Offset.Zero) {
            drawFace(mood, face, if (animate) time else 400L, animate, c.px, c.scr)
        }
    }
}

// ---------------------------------------------------------------- drawing

private class Pen(val ds: DrawScope, val p: Color, val s: Color, val t: Long) {
    fun period(ms: Long) = (t % ms).toFloat() / ms
    fun wave(ms: Long) = sin(period(ms) * 2f * PI.toFloat())

    fun curve(x0: Float, y0: Float, cx: Float, cy: Float, x1: Float, y1: Float, w: Float, color: Color = p) {
        val path = Path().apply { moveTo(x0, y0); quadraticBezierTo(cx, cy, x1, y1) }
        ds.drawPath(path, color, style = Stroke(w, cap = StrokeCap.Round))
    }

    fun poly(vararg pts: Float, color: Color = p) {
        val path = Path().apply {
            moveTo(pts[0], pts[1])
            var i = 2
            while (i < pts.size) { lineTo(pts[i], pts[i + 1]); i += 2 }
            close()
        }
        ds.drawPath(path, color)
    }

    fun disc(x: Float, y: Float, r: Float, color: Color = p) = ds.drawCircle(color, r, Offset(x, y))

    fun heart(cx: Float, cy: Float, sz: Float) {
        val lr = sz * 0.52f
        disc(cx - sz * 0.47f, cy - sz * 0.25f, lr)
        disc(cx + sz * 0.47f, cy - sz * 0.25f, lr)
        poly(cx - sz * 0.98f, cy - sz * 0.05f, cx + sz * 0.98f, cy - sz * 0.05f, cx, cy + sz * 0.95f)
    }

    fun star(cx: Float, cy: Float, r: Float, rot: Float) {
        val path = Path()
        for (i in 0 until 10) {
            val a = -PI.toFloat() / 2 + rot + i * PI.toFloat() / 5
            val rr = if (i % 2 == 0) r else r * 0.45f
            val x = cx + rr * cos(a); val y = cy + rr * sin(a)
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        path.close()
        ds.drawPath(path, p)
    }

    fun spiral(cx: Float, cy: Float, r: Float, rot: Float) {
        val path = Path()
        val n = 60
        for (i in 0..n) {
            val f = i.toFloat() / n
            val a = rot + f * 2.6f * 2f * PI.toFloat()
            val rr = 2f + f * (r - 2f)
            val x = cx + rr * cos(a); val y = cy + rr * sin(a)
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        ds.drawPath(path, p, style = Stroke(2f))
    }

    fun drop(cx: Float, cy: Float, sz: Float) {
        disc(cx, cy, sz)
        poly(cx - sz, cy - 0.3f * sz, cx + sz, cy - 0.3f * sz, cx, cy - 2.4f * sz)
    }

    fun zee(x: Float, y: Float, sz: Float) {
        val path = Path().apply { moveTo(x, y); lineTo(x + sz, y); lineTo(x, y + sz); lineTo(x + sz, y + sz) }
        ds.drawPath(path, p, style = Stroke(1.3f))
    }

    fun sparkle(cx: Float, cy: Float, sz: Float) {
        ds.drawRect(p, Offset(cx - sz, cy - 0.5f), Size(sz * 2 + 1, 1f))
        ds.drawRect(p, Offset(cx - 0.5f, cy - sz), Size(1f, sz * 2 + 1))
    }
}

private fun DrawScope.drawFace(mood: String, face: String, t: Long, animate: Boolean, px: Color, scr: Color) {
    val pen = Pen(this, px, scr, t)
    val look = lookFor(mood, face)
    val m = if (face == "sleep") "sleeping" else mood
    val idle = face == "idle" || face == "boot"

    // whole-face motion
    var bob = sin(t / 900f)
    var ox = 0f
    if (animate && idle) {
        when (m) {
            "happy", "star" -> bob = -2f * abs(pen.wave(600))
            "sleeping" -> bob = 2f * sin(t / 1600f)
            "dizzy" -> ox = 3f * pen.wave(1300)
            "angry" -> if ((t / 1500) % 3 == 0L) ox = if ((t / 40) % 2 == 0L) 1f else -1f
            "love" -> bob = -1.5f * abs(pen.wave(700))
        }
    }
    if (face == "sleep") bob = 2f * sin(t / 1600f)
    if (!animate) bob = 0f

    // gaze: saccades from a time bucket (deterministic, so no state needed)
    var gx = 0f; var gy = 0f
    if (animate && idle) {
        val gxs = floatArrayOf(0f, 6f, -6f, 0f, 0f, 5f, -5f, 4f, -4f, 0f)
        val gys = floatArrayOf(0f, 0f, 0f, -4f, 4f, -3f, -3f, 3f, 3f, 0f)
        val k = (((t / 1700) * 7919) % 10).toInt()
        gx = gxs[k]; gy = gys[k]
        if (m == "nervous") { gx = if ((t / 140) % 2 == 0L) 4f else -4f; gy = 0f }
        if (m == "dizzy" || m == "sleeping") { gx = 0f; gy = 0f }
    } else if (face == "think") {
        gx = 5f + 2f * pen.wave(1400); gy = -5f
    }

    // blink
    var blink = 0f
    if (animate) {
        val periodMs = if (m == "sleepy") 1700L else 3900L
        val ph = t % periodMs
        if (ph < 140) blink = if (ph < 70) ph / 70f else (140 - ph) / 70f
    }

    drawEye(pen, look.l, look.shapeL, EYE_LX + ox, EYE_CY + bob, -1, if (look.shapeL == Shape.EYE) blink else 0f, gx, gy, look.slit && idle)
    drawEye(pen, look.r, look.shapeR, EYE_RX + ox, EYE_CY + bob, 1, if (look.shapeR == Shape.EYE) blink else 0f, gx, gy, look.slit && idle)
    drawMouth(pen, look.mouth)
    if (animate) drawExtras(pen, m, face) else if (m == "cute") drawExtras(pen, m, face)
}

private fun drawEye(pen: Pen, e: EyeP, shape: Shape, cx: Float, cy: Float, side: Int, blink: Float, gx: Float, gy: Float, slit: Boolean) {
    val ds = pen.ds
    when (shape) {
        Shape.HEART -> { pen.heart(cx, cy + 1, 15.5f * (1f + 0.08f * pen.wave(700))); return }
        Shape.STAR -> { pen.star(cx, cy + 1, 19f, 0.18f * pen.wave(1600)); return }
        Shape.SPIRAL -> { pen.spiral(cx, cy + 1, 16f, (if (side < 0) 1 else -1) * pen.period(900) * 2f * PI.toFloat()); return }
        Shape.CLOSED_HAPPY -> { pen.curve(cx - 16, cy + 8, cx, cy - 16, cx + 16, cy + 8, 6f); return }
        Shape.CLOSED_SLEEP -> { pen.curve(cx - 15, cy + 3, cx, cy + 13, cx + 15, cy + 3, 4f); return }
        Shape.EYE -> {}
    }
    val w = e.w; val h = e.h
    val x = cx - w / 2; val y = cy - h / 2 + e.dy
    val rr = min(e.r, min(w, h) / 2 - 1)

    // white
    ds.drawRoundRect(pen.p, Offset(x, y), Size(w, h), CornerRadius(rr))

    // pupil + highlight
    if (e.pupR > 0.5f) {
        val mx = w / 2 - e.pupR - 3; val my = h / 2 - e.pupR - 3
        val px = (cx + gx + e.pupDX).coerceIn(cx - mx, cx + mx)
        val py = (y + h / 2 + gy + e.pupDY).coerceIn(y + h / 2 - my, y + h / 2 + my)
        pen.disc(px, py, e.pupR, pen.s)
        pen.disc(px - e.pupR * 0.4f, py - e.pupR * 0.4f, if (e.pupR >= 9) 3f else 2f)
        if (e.pupR >= 9) pen.disc(px + e.pupR * 0.35f, py + e.pupR * 0.3f, 1f)
    }
    if (slit) {
        ds.drawOval(pen.s, Offset(cx + gx * 0.6f - 3f, y + 4f), Size(6f, h - 8f))
    }

    // lids
    val inC = max(e.lidIn, blink); val outC = max(e.lidOut, blink)
    if (inC > 0.01f || outC > 0.01f) {
        val xi = (if (side < 0) x + w else x) - side * 2
        val xo = (if (side < 0) x else x + w) + side * 2
        val top = y - 2
        pen.poly(xo, top, xi, top, xi, y + inC * h, xo, y + outC * h, color = pen.s)
        if (blink > 0.85f) {
            ds.drawRect(pen.s, Offset(x - 2, y - 2), Size(w + 4, h + 4))
            ds.drawRect(pen.p, Offset(x + 3, y + h * 0.6f), Size(w - 6, 3f))
        }
    }
}

private fun drawMouth(pen: Pen, m: Mouth) {
    val ds = pen.ds
    val cx = 64f; val y = MOUTH_Y
    when (m) {
        Mouth.SMALL -> pen.curve(cx - 6, y, cx, y + 3, cx + 6, y, 2f)
        Mouth.SMILE -> pen.curve(cx - 9, y - 2, cx, y + 6, cx + 9, y - 2, 3f)
        Mouth.GRIN -> {
            val path = Path().apply { moveTo(cx - 11, y - 3); lineTo(cx + 11, y - 3); quadraticBezierTo(cx, y + 13, cx - 11, y - 3); close() }
            ds.drawPath(path, pen.p)
        }
        Mouth.FROWN -> pen.curve(cx - 8, y + 3, cx, y - 4, cx + 8, y + 3, 3f)
        Mouth.O -> { pen.disc(cx, y + 1, 5f); pen.disc(cx, y + 1, 2f, pen.s) }
        Mouth.TINY_O -> pen.disc(cx, y + 1, 2f)
        Mouth.WAVY -> {
            val ph = pen.period(500) * 2f * PI.toFloat()
            val path = Path()
            for (i in -10..10) {
                val yy = y + 2.2f * sin(i * 0.75f + ph)
                if (i == -10) path.moveTo(cx + i, yy) else path.lineTo(cx + i, yy)
            }
            ds.drawPath(path, pen.p, style = Stroke(1.6f))
        }
        Mouth.SMIRK -> pen.curve(cx - 7, y + 1, cx + 2, y + 3, cx + 9, y - 3, 2f)
        Mouth.CAT -> {
            pen.curve(cx - 8, y - 1, cx - 4, y + 4, cx, y - 1, 2f)
            pen.curve(cx, y - 1, cx + 4, y + 4, cx + 8, y - 1, 2f)
        }
        Mouth.TALK -> {
            val open = 2f + 7f * abs(sin(pen.t / 95f) * sin(pen.t / 230f))
            ds.drawRoundRect(pen.p, Offset(cx - 7, y - open / 2), Size(14f, open + 2), CornerRadius(2f))
        }
        Mouth.NONE -> {}
    }
}

private fun drawExtras(pen: Pen, m: String, face: String) {
    val ds = pen.ds
    val t = pen.t
    when (face) {
        "listen" -> {
            for (i in 0 until 3) {
                val hgt = 3f + 7f * abs(sin(t / (110f + i * 37) + i))
                ds.drawRect(pen.p, Offset(56f + i * 7, MOUTH_Y + 5 - hgt), Size(4f, hgt))
            }
            return
        }
        "think" -> {
            val n = ((t / 350) % 4).toInt()
            for (i in 0 until n) pen.disc(100f + i * 7, 56f, 1.2f)
            return
        }
        "notify" -> {
            val b = 2f * abs(pen.wave(400))
            ds.drawRect(pen.p, Offset(62f, 1 + b), Size(4f, 7f))
            ds.drawRect(pen.p, Offset(62f, 10 + b), Size(4f, 3f))
            return
        }
        "speak" -> return
    }
    when (m) {
        "love" -> for (i in 0 until 2) {
            val f = pen.period(2200L + i * 500)
            val x = if (i == 0) 8f + 3f * sin(f * 6) else 120f + 3f * sin(f * 6 + 1)
            pen.heart(x, 52f - f * 44f, 3f)
        }
        "star" -> {
            val sx = floatArrayOf(10f, 117f, 64f); val sy = floatArrayOf(8f, 12f, 4f)
            for (i in 0 until 3) if (((t / 260) + i) % 3 != 0L) pen.sparkle(sx[i], sy[i], 2f)
        }
        "sad" -> { val f = pen.period(2600); if (f < 0.7f) pen.drop(EYE_LX - 10, 44f + f * 26f, 2f) }
        "nervous" -> pen.drop(EYE_RX + 19, 8f + pen.period(1800) * 14f, 2.2f)
        "angry" -> if ((t / 300) % 2 == 1L) {
            ds.drawCircle(pen.p, 2f, Offset(118f, 6f), style = Stroke(1f))
            ds.drawCircle(pen.p, 1f, Offset(124f, 11f), style = Stroke(1f))
        }
        "cute" -> for (i in 0 until 3) {
            for (ex in listOf(EYE_LX - 12, EYE_RX - 2)) {
                val path = Path().apply { moveTo(ex + i * 5, 50f); lineTo(ex + 2 + i * 5, 47f) }
                ds.drawPath(path, pen.p, style = Stroke(1f))
            }
        }
        "sleeping" -> for (i in 0 until 2) {
            val f = pen.period(2400L + i * 300)
            pen.zee(104f + i * 9 + f * 4, 22f - f * 18f - i * 4, 4f + i * 2)
        }
        "sleepy" -> { val f = pen.period(3000); pen.zee(110f + f * 4, 14f - f * 10f, 5f) }
    }
}
