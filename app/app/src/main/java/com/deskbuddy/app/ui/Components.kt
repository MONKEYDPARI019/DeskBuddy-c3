package com.deskbuddy.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.setProgress
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deskbuddy.app.R
import kotlin.math.ceil
import kotlin.math.roundToInt

// Kawaii building blocks, matching the components in the Figma file (Toggle, Segment, Button,
// Tab item, Stat tile, Action, Mood tile, Notification, Setting row).

// ---------------------------------------------------------------- basics

/** Soft drop shadow in the theme's glow colour (pink in light, black in dark). */
fun Modifier.glow(pal: Pal, shape: Shape, elevation: Dp = 6.dp): Modifier =
    this.shadow(elevation, shape, clip = false, ambientColor = pal.glow, spotColor = pal.glow)

/** Titles and big numbers: Fredoka SemiBold. */
@Composable
fun HeadText(
    text: String,
    size: TextUnit,
    color: Color = LocalPal.current.ink,
    modifier: Modifier = Modifier,
    maxLines: Int = Int.MAX_VALUE,
    align: TextAlign = TextAlign.Start,
) {
    BasicText(
        text = text,
        modifier = modifier,
        style = TextStyle(
            fontFamily = HeadFont, fontWeight = FontWeight.SemiBold, fontSize = size,
            color = color, lineHeight = size * 1.2f, textAlign = align,
        ),
        overflow = TextOverflow.Ellipsis,
        maxLines = maxLines,
    )
}

/** Everything else: Nunito Regular or Bold. */
@Composable
fun BodyText(
    text: String,
    size: TextUnit = 14.sp,
    color: Color = LocalPal.current.ink,
    modifier: Modifier = Modifier,
    bold: Boolean = false,
    maxLines: Int = Int.MAX_VALUE,
    align: TextAlign = TextAlign.Start,
) {
    BasicText(
        text = text,
        modifier = modifier,
        style = TextStyle(
            fontFamily = BodyFont, fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal,
            fontSize = size, color = color, lineHeight = size * 1.35f, textAlign = align,
        ),
        overflow = TextOverflow.Ellipsis,
        maxLines = maxLines,
    )
}

/** A line icon from res/drawable (ic_*), tinted. */
@Composable
fun Glyph(res: Int, size: Dp, tint: Color, modifier: Modifier = Modifier) {
    Image(
        painter = painterResource(res),
        contentDescription = null,
        modifier = modifier.size(size),
        colorFilter = ColorFilter.tint(tint),
    )
}

/** Mochi's face for each mood, as drawn in Figma (res/drawable/face_*). */
fun faceRes(mood: String): Int = when (mood) {
    "happy" -> R.drawable.face_happy
    "love" -> R.drawable.face_love
    "star" -> R.drawable.face_star
    "wink" -> R.drawable.face_wink
    "dizzy" -> R.drawable.face_dizzy
    "angry" -> R.drawable.face_angry
    "sad" -> R.drawable.face_sad
    "sleepy" -> R.drawable.face_sleepy
    "surprised" -> R.drawable.face_surprised
    "smug" -> R.drawable.face_smug
    "nervous" -> R.drawable.face_nervous
    "cat" -> R.drawable.face_cat
    "sleeping" -> R.drawable.face_sleeping
    "cute" -> R.drawable.face_cute
    else -> R.drawable.face_default
}

/** Small rounded label with a coloured dot ("Linked", "Happy", "Now: happy"). */
@Composable
fun Chip(text: String, bg: Color, dot: Color) {
    Row(
        Modifier
            .clip(RoundedCornerShape(14.dp))
            .background(bg)
            .padding(start = 10.dp, end = 12.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.size(8.dp).background(dot, CircleShape))
        BodyText(text, 12.sp, bold = true, maxLines = 1)
    }
}

// ---------------------------------------------------------------- controls

enum class Kind { PRIMARY, SOFT, OUTLINE }

@Composable
fun KButton(text: String, modifier: Modifier = Modifier, kind: Kind = Kind.SOFT, onClick: () -> Unit) {
    val c = LocalPal.current
    val shape = RoundedCornerShape(18.dp)
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val look = when (kind) {
        Kind.PRIMARY -> Modifier.glow(c, shape, 4.dp).background(c.accent, shape)
        Kind.SOFT -> Modifier.background(c.surface2, shape)
        Kind.OUTLINE -> Modifier.border(2.dp, c.accent, shape)
    }
    Box(
        modifier
            .defaultMinSize(minHeight = 44.dp)
            .scale(if (pressed) 0.97f else 1f)
            .then(look)
            .clip(shape)
            .clickable(interactionSource = src, indication = null, role = Role.Button, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        BodyText(text, 15.sp, if (kind == Kind.PRIMARY) c.accentInk else c.ink, bold = true, maxLines = 1, align = TextAlign.Center)
    }
}

/** Pill track with equal-width options, one selected (screens, link, sleep timer, theme). */
@Composable
fun Segmented(options: List<Pair<String, String>>, value: String, onPick: (String) -> Unit) {
    val c = LocalPal.current
    val tight = options.size > 3
    Row(
        Modifier
            .fillMaxWidth()
            .background(c.surface2, RoundedCornerShape(18.dp))
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        options.forEach { (id, label) ->
            val on = id == value
            val shape = RoundedCornerShape(14.dp)
            Box(
                Modifier
                    .weight(1f)
                    .then(if (on) Modifier.glow(c, shape, 3.dp).background(c.accent, shape) else Modifier)
                    .clip(shape)
                    .selectable(selected = on, role = Role.RadioButton) { onPick(id) }
                    .padding(horizontal = if (tight) 2.dp else 10.dp, vertical = 9.dp),
                contentAlignment = Alignment.Center,
            ) {
                BodyText(label, if (tight) 13.sp else 14.sp, if (on) c.accentInk else c.sub, bold = true, maxLines = 1, align = TextAlign.Center)
            }
        }
    }
}

/** The switch itself (no touch handling: the whole SettingRow is the touch target). */
@Composable
fun KSwitch(on: Boolean) {
    val c = LocalPal.current
    Box(
        Modifier
            .size(46.dp, 28.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(if (on) c.accent else c.line)
            .padding(3.dp),
        contentAlignment = if (on) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        Box(Modifier.size(22.dp).shadow(1.dp, CircleShape).background(c.surface, CircleShape))
    }
}

/** Label on the left, switch on the right; tapping anywhere on the row flips it. */
@Composable
fun SettingRow(label: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 40.dp)
            .clip(RoundedCornerShape(12.dp))
            .toggleable(value = on, role = Role.Switch, onValueChange = onChange)
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        BodyText(label, 15.sp, modifier = Modifier.weight(1f))
        KSwitch(on)
    }
}

/** 10-step slider (buzzer / volume, brightness): tap or drag; level 1..10. */
@Composable
fun StepSlider(label: String, level: Int, valueText: String, onPick: (Int) -> Unit) {
    val c = LocalPal.current
    val pick by rememberUpdatedState(onPick)
    val current by rememberUpdatedState(level)
    var width by remember { mutableIntStateOf(1) }
    fun levelAt(x: Float): Int = ceil(x / width * 10f).toInt().coerceIn(1, 10)
    val frac = level.coerceIn(0, 10) / 10f
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            BodyText(label, 14.sp, bold = true, modifier = Modifier.weight(1f))
            BodyText(valueText, 13.sp, c.sub)
        }
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(24.dp)
                .onSizeChanged { width = it.width.coerceAtLeast(1) }
                .pointerInput(Unit) { detectTapGestures { pick(levelAt(it.x)) } }      // a tap always sends, like before
                .pointerInput(Unit) {
                    var last = 0                                               // a drag sends each new step once
                    detectHorizontalDragGestures(onDragStart = { last = current }) { change, _ ->
                        change.consume()
                        val l = levelAt(change.position.x)
                        if (l != last) { last = l; pick(l) }
                    }
                }
                .semantics {
                    contentDescription = label
                    stateDescription = valueText
                    progressBarRangeInfo = ProgressBarRangeInfo(frac, 0f..1f, 9)
                    setProgress { target -> pick((target * 10f).roundToInt().coerceIn(1, 10)); true }
                }
        ) {
            val h = 10.dp.toPx()
            val y = (size.height - h) / 2f
            val r = CornerRadius(h / 2f)
            val thumb = 10.dp.toPx()
            val ring = 3.dp.toPx()
            val cx = (size.width * frac).coerceIn(thumb, maxOf(thumb, size.width - thumb))
            drawRoundRect(c.surface2, Offset(0f, y), Size(size.width, h), r)
            drawRoundRect(c.accent, Offset(0f, y), Size(cx, h), r)
            drawCircle(c.surface, thumb - ring / 2f, Offset(cx, size.height / 2f))
            drawCircle(c.accent, thumb - ring / 2f, Offset(cx, size.height / 2f), style = Stroke(ring))
        }
    }
}

@Composable
fun KField(value: String, onChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, number: Boolean = false) {
    val c = LocalPal.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(5.dp)) {
        BodyText(label.uppercase(), 11.sp, c.sub, bold = true)
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            textStyle = TextStyle(fontFamily = BodyFont, fontWeight = FontWeight.Normal, fontSize = 14.sp, color = c.ink),
            cursorBrush = SolidColor(c.accent),
            keyboardOptions = KeyboardOptions(keyboardType = if (number) KeyboardType.Number else KeyboardType.Text),
            modifier = Modifier
                .fillMaxWidth()
                .background(c.surface2, RoundedCornerShape(14.dp))
                .padding(horizontal = 12.dp, vertical = 11.dp)
                .semantics { contentDescription = label },
        )
    }
}

// ---------------------------------------------------------------- layout

/** White rounded card with a soft glow; optional Fredoka title. */
@Composable
fun KCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = LocalPal.current
    val shape = RoundedCornerShape(24.dp)
    Column(
        modifier
            .fillMaxWidth()
            .glow(c, shape)
            .background(c.surface, shape)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (title != null) HeadText(title, 16.sp)
        content()
    }
}

/** Pastel tile on Home: icon, small label, then the value (see TileValue). */
@Composable
fun StatTile(icon: Int, label: String, tint: Color, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = LocalPal.current
    Column(
        modifier
            .background(tint, RoundedCornerShape(20.dp))
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Glyph(icon, 20.dp, c.ink)
        BodyText(label, 12.sp, c.sub, maxLines = 1)
        content()
    }
}

@Composable
fun TileValue(text: String, extra: String? = null, size: TextUnit = 19.sp) {
    HeadText(text, size, maxLines = 1)
    if (!extra.isNullOrEmpty()) BodyText(extra, 12.sp, LocalPal.current.sub, maxLines = 1)
}

/** Outlined square-ish button with an icon on top (Sound, Ping, Zzz). */
@Composable
fun ActionTile(icon: Int, label: String, modifier: Modifier = Modifier, active: Boolean = false, onClick: () -> Unit) {
    val c = LocalPal.current
    val shape = RoundedCornerShape(20.dp)
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val fg = if (active) c.accentInk else c.ink
    Column(
        modifier
            .scale(if (pressed) 0.96f else 1f)
            .background(if (active) c.accent else c.surface, shape)
            .border(1.5.dp, if (active) c.accent else c.line, shape)
            .clip(shape)
            .clickable(interactionSource = src, indication = null, role = Role.Button, onClick = onClick)
            .padding(vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Glyph(icon, 24.dp, fg)
        BodyText(label, 13.sp, fg, bold = true, maxLines = 1)
    }
}

@Composable
fun ScreenTitle(title: String, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        HeadText(title, 28.sp, modifier = Modifier.weight(1f), maxLines = 1)
        trailing()
    }
}

@Composable
fun Header(connected: Boolean, dark: Boolean, onToggleTheme: () -> Unit) {
    val c = LocalPal.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(c.bg)
            .padding(horizontal = 20.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).background(c.oled, RoundedCornerShape(13.dp)), contentAlignment = Alignment.Center) {
            Image(painterResource(R.drawable.face_cute), contentDescription = null, modifier = Modifier.size(33.6.dp, 22.4.dp))
        }
        HeadText("DeskBuddy", 22.sp, modifier = Modifier.weight(1f).padding(start = 10.dp), maxLines = 1)
        Chip(if (connected) "Linked" else "Offline", if (connected) c.mint else c.surface2, if (connected) c.accent else c.sub)
        // 36 dp circle in a 46 dp touch area
        Box(
            Modifier
                .padding(start = 3.dp)
                .size(46.dp)
                .clip(CircleShape)
                .clickable(role = Role.Button, onClickLabel = if (dark) "Switch to light theme" else "Switch to dark theme") { onToggleTheme() },
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier.size(36.dp).background(c.surface, CircleShape).border(1.5.dp, c.line, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Glyph(if (dark) R.drawable.ic_sun else R.drawable.ic_moon, 18.dp, c.ink)
            }
        }
    }
}

/** Floating rounded tab bar. Voice is only there for DeskBuddy v2 (the C3 has no mic or speaker). */
@Composable
fun TabBar(active: String, showVoice: Boolean, onPick: (String) -> Unit) {
    val c = LocalPal.current
    val tabs = buildList {
        add(Triple("home", "Home", R.drawable.ic_home))
        add(Triple("moods", "Moods", R.drawable.ic_smile))
        add(Triple("inbox", "Inbox", R.drawable.ic_inbox))
        if (showVoice) add(Triple("voice", "Voice", R.drawable.ic_mic))
        add(Triple("setup", "Setup", R.drawable.ic_sliders))
    }
    val bar = RoundedCornerShape(28.dp)
    Box(
        Modifier
            .fillMaxWidth()
            .background(c.bg)
            .padding(start = 14.dp, end = 14.dp, top = 6.dp, bottom = 16.dp)
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .glow(c, bar, 8.dp)
                .background(c.surface, bar)
                .padding(8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            tabs.forEach { (id, label, icon) ->
                val on = id == active
                val fg = if (on) c.accentInk else c.sub
                Column(
                    Modifier
                        .clip(RoundedCornerShape(20.dp))
                        .background(if (on) c.accent else Color.Transparent)
                        .selectable(selected = on, role = Role.Tab) { onPick(id) }
                        .padding(horizontal = if (tabs.size > 4) 9.dp else 14.dp, vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Glyph(icon, 22.dp, fg)
                    BodyText(label, 11.sp, fg, bold = true, maxLines = 1)
                }
            }
        }
    }
}
