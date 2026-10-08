package com.deskbuddy.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ---------------------------------------------------------------- basics

/** Hard-edged retro box: optional offset shadow, fill, thick border. */
fun Modifier.pixelFrame(bg: Color, border: Color, shadow: Color?, shadowDp: Dp = 4.dp, borderDp: Dp = 3.dp): Modifier =
    this
        .drawBehind {
            if (shadow != null) {
                val o = shadowDp.toPx()
                drawRect(shadow, topLeft = Offset(o, o), size = size)
            }
        }
        .background(bg)
        .border(borderDp, border)

@Composable
fun PxText(text: String, size: TextUnit = 9.sp, color: Color = LocalPal.current.ink, modifier: Modifier = Modifier, align: TextAlign? = null) {
    BasicText(
        text, modifier,
        style = TextStyle(fontFamily = PixelFont, fontSize = size, color = color, lineHeight = size * 1.5f, textAlign = align ?: TextAlign.Start)
    )
}

@Composable
fun TermText(text: String, size: TextUnit = 22.sp, color: Color = LocalPal.current.ink, modifier: Modifier = Modifier, maxLines: Int = Int.MAX_VALUE) {
    BasicText(
        text, modifier,
        style = TextStyle(fontFamily = TermFont, fontSize = size, color = color, lineHeight = size * 1.05f),
        maxLines = maxLines
    )
}

/** 8x8 pixel-art icon; '#' = filled cell. */
@Composable
fun PixelIcon(rows: List<String>, dp: Dp, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier.size(dp)) {
        val cell = size.width / 8f
        rows.forEachIndexed { y, row ->
            row.forEachIndexed { x, ch ->
                if (ch == '#') drawRect(color, Offset(x * cell, y * cell), Size(cell + 0.5f, cell + 0.5f))
            }
        }
    }
}

object Icons {
    val home = listOf("...##...", "..####..", ".######.", "########", ".##..##.", ".##..##.", ".######.", "........")
    val moods = listOf(".######.", "#......#", "#.#..#.#", "#......#", "#......#", "#.####.#", "#......#", ".######.")
    val inbox = listOf("........", "########", "##....##", "#.#..#.#", "#..##..#", "#......#", "########", "........")
    val voice = listOf("...##...", "..####..", "..####..", "..####..", "#.####.#", ".#....#.", "..####..", "...##...")
    val setup = listOf("..#..#..", ".######.", "##....##", ".#.##.#.", ".#.##.#.", "##....##", ".######.", "..#..#..")
    val sun = listOf("...##...", ".#....#.", "..####..", "#.####.#", "#.####.#", "..####..", ".#....#.", "...##...")
    val moon = listOf("..####..", ".##.....", "##......", "##......", "##......", "##.....#", ".##...##", "..####..")
}

// ---------------------------------------------------------------- controls

@Composable
fun PixelButton(
    text: String,
    modifier: Modifier = Modifier,
    active: Boolean = false,
    fontSize: TextUnit = 9.sp,
    minHeight: Dp = 48.dp,
    term: Boolean = false,
    onClick: () -> Unit,
) {
    val c = LocalPal.current
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val fg = if (active) c.onAcc else c.ink
    Box(
        modifier
            .defaultMinSize(minHeight = minHeight)
            .offset(if (pressed) 2.dp else 0.dp, if (pressed) 2.dp else 0.dp)
            .pixelFrame(if (active) c.acc else c.panel, c.ink, if (pressed || active) null else c.line)
            .clickable(interactionSource = src, indication = null, role = Role.Button, onClick = onClick)
            .padding(horizontal = 6.dp, vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        if (term) TermText(text, fontSize, fg) else PxText(text, fontSize, fg, align = TextAlign.Center)
    }
}

/** Row of equal-width options, one selected (screens, sleep timer, theme). */
@Composable
fun OptionRow(options: List<Pair<String, String>>, selected: String, term: Boolean = true, onPick: (String) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (id, label) ->
            PixelButton(
                label, Modifier.weight(1f), active = id == selected,
                fontSize = if (term) 19.sp else 8.sp, minHeight = 46.dp, term = term
            ) { onPick(id) }
        }
    }
}

@Composable
fun PixelToggle(on: Boolean, label: String, onChange: (Boolean) -> Unit) {
    val c = LocalPal.current
    Box(
        Modifier
            .size(66.dp, 36.dp)
            .background(if (on) c.acc else c.soft)
            .border(3.dp, c.ink)
            .toggleable(value = on, role = Role.Switch, onValueChange = onChange)
            .semantics { contentDescription = label }
            .padding(4.dp),
        contentAlignment = if (on) Alignment.CenterEnd else Alignment.CenterStart
    ) {
        Box(Modifier.size(22.dp).background(if (on) c.onAcc else c.ink))
    }
}

@Composable
fun ToggleRow(label: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp), verticalAlignment = Alignment.CenterVertically) {
        TermText(label, 23.sp, modifier = Modifier.weight(1f))
        PxText(if (on) "ON" else "OFF", 8.sp, LocalPal.current.sub, Modifier.padding(end = 10.dp))
        PixelToggle(on, label, onChange)
    }
}

/** 10-step segmented level control (volume, brightness). */
@Composable
fun SegmentBar(label: String, level: Int, valueText: String, onPick: (Int) -> Unit) {
    val c = LocalPal.current
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth()) {
            PxText(label, 8.sp, modifier = Modifier.weight(1f))
            TermText(valueText, 20.sp, c.sub)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            for (i in 1..10) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(36.dp)
                        .background(if (i <= level) c.acc else c.soft)
                        .border(2.dp, c.ink)
                        .clickable(role = Role.Button, onClickLabel = "$label ${i * 10}%") { onPick(i) }
                )
            }
        }
    }
}

@Composable
fun PixelField(value: String, onChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, number: Boolean = false) {
    val c = LocalPal.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        PxText(label, 8.sp)
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            textStyle = TextStyle(fontFamily = TermFont, fontSize = 24.sp, color = c.ink),
            cursorBrush = SolidColor(c.acc),
            keyboardOptions = KeyboardOptions(keyboardType = if (number) KeyboardType.Number else KeyboardType.Text),
            modifier = Modifier
                .fillMaxWidth()
                .background(c.soft)
                .border(3.dp, c.ink)
                .padding(horizontal = 10.dp, vertical = 8.dp)
                .semantics { contentDescription = label }
        )
    }
}

// ---------------------------------------------------------------- layout

@Composable
fun PixelCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = LocalPal.current
    Column(
        modifier
            .fillMaxWidth()
            .pixelFrame(c.panel, c.ink, c.line, 5.dp)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (title != null) PxText(title, 9.sp, c.sub)
        content()
    }
}

@Composable
fun StatTile(label: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    val c = LocalPal.current
    Column(
        modifier.background(c.panel).border(3.dp, c.ink).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        PxText(label, 8.sp, c.sub)
        content()
    }
}

@Composable
fun ScreenTitle(title: String, trailing: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        PxText(title, 16.sp, modifier = Modifier.weight(1f))
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
            .drawBehind {
                val w = 3.dp.toPx()
                drawRect(c.ink, Offset(0f, size.height - w), Size(size.width, w))
            }
            .padding(start = 20.dp, end = 16.dp, top = 14.dp, bottom = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        PxText("DESKBUDDY", 13.sp, modifier = Modifier.weight(1f))
        Box(Modifier.size(10.dp).background(if (connected) c.acc else c.sub))
        TermText(if (connected) "LINKED" else "OFFLINE", 22.sp, c.sub, Modifier.padding(start = 8.dp, end = 12.dp))
        Box(
            Modifier
                .size(44.dp)
                .background(c.panel)
                .border(3.dp, c.ink)
                .clickable(role = Role.Button, onClickLabel = if (dark) "Switch to light theme" else "Switch to dark theme") { onToggleTheme() },
            contentAlignment = Alignment.Center
        ) {
            PixelIcon(if (dark) Icons.sun else Icons.moon, 22.dp, c.ink)
        }
    }
}

@Composable
fun TabBar(active: String, onPick: (String) -> Unit) {
    val c = LocalPal.current
    val tabs = listOf(
        Triple("home", "HOME", Icons.home), Triple("moods", "MOODS", Icons.moods), Triple("inbox", "INBOX", Icons.inbox),
        Triple("voice", "VOICE", Icons.voice), Triple("setup", "SETUP", Icons.setup)
    )
    Row(
        Modifier
            .fillMaxWidth()
            .height(80.dp)
            .background(c.bg)
            .drawBehind { drawRect(c.ink, Offset.Zero, Size(size.width, 3.dp.toPx())) }
            .padding(top = 3.dp)
    ) {
        tabs.forEach { (id, label, icon) ->
            val on = id == active
            val fg = if (on) c.onAcc else c.ink
            Column(
                Modifier
                    .weight(1f)
                    .height(77.dp)
                    .background(if (on) c.acc else c.bg)
                    .clickable(role = Role.Tab, onClickLabel = label) { onPick(id) },
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                PixelIcon(icon, 24.dp, fg)
                PxText(label, 7.sp, fg, Modifier.padding(top = 8.dp))
            }
        }
    }
}
