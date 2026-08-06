"""
Lebanese Ms. Pac-Man
A classic arcade game with Lebanese cultural themes!

Controls:
    Arrow keys - Move
    ESC - Quit
    ENTER - Start / Restart
"""

import pygame
import sys
import math
import random
from enum import Enum, auto
from copy import deepcopy

# =====================================================================
#  CONSTANTS
# =====================================================================

TILE = 24
COLS = 28
ROWS = 27
HUD_H = 80
WIDTH = TILE * COLS
HEIGHT = TILE * ROWS + HUD_H
FPS = 60

# Speeds (pixels per frame – must divide evenly into TILE)
PLAYER_SPEED = 2
GHOST_SPEED = 2
FRIGHT_SPEED = 1
EATEN_SPEED = 4

# Timing (frames)
FRIGHT_DUR = 7 * FPS
FRIGHT_WARN = 3 * FPS  # start flashing 3s before end
SCATTER_DUR = [7 * FPS, 7 * FPS, 5 * FPS, 5 * FPS]
CHASE_DUR = [20 * FPS, 20 * FPS, 20 * FPS, None]
RELEASE_INTERVAL = 3 * FPS
READY_DUR = 2 * FPS
DEATH_DUR = 60
LEVEL_DUR = 90

# Scoring
DOT_PTS = 10
POWER_PTS = 50
GHOST_PTS = [200, 400, 800, 1600]
LIVES = 3

# --------------- colours (Lebanese palette) ---------------
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
CEDAR = (0, 128, 55)
DARK_CEDAR = (0, 80, 30)
LEB_RED = (237, 28, 36)
RED = (255, 0, 0)
PINK = (255, 184, 255)
CYAN = (0, 255, 255)
ORANGE = (255, 184, 82)
FRIGHT_BLUE = (33, 33, 255)
HUMMUS = (210, 180, 140)
MANOUSHE = (180, 120, 60)
DOOR_COL = (255, 183, 197)
BG = (10, 10, 30)

# --------------- tile types ---------------
W = 0   # wall
D = 1   # dot (hummus)
P = 2   # power pellet (manoushe)
E = 3   # empty path
G = 4   # ghost-house interior
R = 5   # ghost-house door
V = 6   # void (outside play area)

MAZE_TEMPLATE = [
    [W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W],
    [W,D,D,D,D,D,D,D,D,D,D,D,D,W,W,D,D,D,D,D,D,D,D,D,D,D,D,W],
    [W,D,W,W,W,W,D,W,W,W,W,W,D,W,W,D,W,W,W,W,W,D,W,W,W,W,D,W],
    [W,P,W,W,W,W,D,W,W,W,W,W,D,W,W,D,W,W,W,W,W,D,W,W,W,W,P,W],
    [W,D,W,W,W,W,D,W,W,W,W,W,D,W,W,D,W,W,W,W,W,D,W,W,W,W,D,W],
    [W,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,W],
    [W,D,W,W,W,W,D,W,W,D,W,W,W,W,W,W,W,W,D,W,W,D,W,W,W,W,D,W],
    [W,D,D,D,D,D,D,W,W,D,D,D,D,W,W,D,D,D,D,W,W,D,D,D,D,D,D,W],
    [W,W,W,W,W,W,D,W,W,W,W,W,E,W,W,E,W,W,W,W,W,D,W,W,W,W,W,W],
    [V,V,V,V,V,W,D,W,W,W,W,W,E,W,W,E,W,W,W,W,W,D,W,V,V,V,V,V],
    [V,V,V,V,V,W,D,W,W,E,E,E,E,E,E,E,E,E,E,W,W,D,W,V,V,V,V,V],
    [V,V,V,V,V,W,D,W,W,E,W,W,W,R,R,W,W,W,E,W,W,D,W,V,V,V,V,V],
    [W,W,W,W,W,W,D,W,W,E,W,G,G,G,G,G,G,W,E,W,W,D,W,W,W,W,W,W],
    [E,E,E,E,E,E,D,E,E,E,W,G,G,G,G,G,G,W,E,E,E,D,E,E,E,E,E,E],
    [W,W,W,W,W,W,D,W,W,E,W,G,G,G,G,G,G,W,E,W,W,D,W,W,W,W,W,W],
    [V,V,V,V,V,W,D,W,W,E,W,W,W,W,W,W,W,W,E,W,W,D,W,V,V,V,V,V],
    [V,V,V,V,V,W,D,W,W,E,E,E,E,E,E,E,E,E,E,W,W,D,W,V,V,V,V,V],
    [V,V,V,V,V,W,D,W,W,E,W,W,W,W,W,W,W,W,E,W,W,D,W,V,V,V,V,V],
    [W,W,W,W,W,W,D,W,W,E,W,W,W,W,W,W,W,W,E,W,W,D,W,W,W,W,W,W],
    [W,D,D,D,D,D,D,D,D,D,D,D,D,W,W,D,D,D,D,D,D,D,D,D,D,D,D,W],
    [W,D,W,W,W,W,D,W,W,W,W,W,D,W,W,D,W,W,W,W,W,D,W,W,W,W,D,W],
    [W,P,D,D,W,W,D,D,D,D,D,D,D,E,E,D,D,D,D,D,D,D,W,W,D,D,P,W],
    [W,W,W,D,W,W,D,W,W,D,W,W,W,W,W,W,W,W,D,W,W,D,W,W,D,W,W,W],
    [W,D,D,D,D,D,D,W,W,D,D,D,D,W,W,D,D,D,D,W,W,D,D,D,D,D,D,W],
    [W,D,W,W,W,W,W,W,W,W,W,W,D,W,W,D,W,W,W,W,W,W,W,W,W,W,D,W],
    [W,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,D,W],
    [W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W,W],
]

PLAYER_START = (14, 21)

GHOST_DEFS = [
    # name,      colour, scatter corner, start (col,row), in_house
    ("Byblos",   RED,    (25, 0),  (13, 10), False),
    ("Sidon",    PINK,   (2,  0),  (13, 13), True),
    ("Tyre",     CYAN,   (27, 26), (11, 13), True),
    ("Baalbek",  ORANGE, (0,  26), (15, 13), True),
]

BONUS_FOODS = ["Falafel", "Shawarma", "Kibbeh", "Baklava", "Cedar"]
BONUS_SCORES = [100, 300, 500, 700, 1000]


# =====================================================================
#  DIRECTIONS
# =====================================================================

class Dir(Enum):
    NONE  = (0, 0)
    UP    = (0, -1)
    DOWN  = (0, 1)
    LEFT  = (-1, 0)
    RIGHT = (1, 0)

OPPOSITE = {
    Dir.UP: Dir.DOWN, Dir.DOWN: Dir.UP,
    Dir.LEFT: Dir.RIGHT, Dir.RIGHT: Dir.LEFT,
    Dir.NONE: Dir.NONE,
}

class GMode(Enum):
    SCATTER = auto()
    CHASE   = auto()
    FRIGHT  = auto()
    EATEN   = auto()

class State(Enum):
    TITLE    = auto()
    READY    = auto()
    PLAYING  = auto()
    DYING    = auto()
    GAMEOVER = auto()
    LEVELUP  = auto()


# =====================================================================
#  HELPERS
# =====================================================================

def walkable_player(tile):
    return tile in (D, P, E)

def walkable_ghost(tile, exiting_house=False, eaten=False):
    if eaten:
        return tile not in (W, V)
    if exiting_house:
        return tile in (D, P, E, R, G)
    return tile in (D, P, E)

def tile_at(maze, col, row):
    if row < 0 or row >= ROWS:
        return W
    c = col % COLS  # tunnel wrap
    return maze[row][c]

def dist_sq(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


# =====================================================================
#  DRAW HELPERS
# =====================================================================

def draw_pacman(surf, cx, cy, direction, mouth_angle, size=TILE - 4):
    """Draw Ms. Pac-Man (yellow circle with mouth + pink bow)."""
    r = size // 2
    angle_map = {Dir.RIGHT: 0, Dir.LEFT: 180, Dir.UP: 90, Dir.DOWN: 270, Dir.NONE: 0}
    base = angle_map[direction]
    start = math.radians(base + mouth_angle)
    end = math.radians(base + 360 - mouth_angle)

    # body
    points = [(cx, cy)]
    steps = 30
    for i in range(steps + 1):
        a = start + (end - start) * i / steps
        points.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    if len(points) > 2:
        pygame.draw.polygon(surf, YELLOW, points)

    # pink bow / ribbon on top
    bow_r = r // 3
    bx, by = cx, cy - r + 1
    pygame.draw.circle(surf, PINK, (int(bx - bow_r), int(by)), bow_r)
    pygame.draw.circle(surf, PINK, (int(bx + bow_r), int(by)), bow_r)
    pygame.draw.circle(surf, LEB_RED, (int(bx), int(by)), bow_r // 2 + 1)


def draw_ghost(surf, cx, cy, colour, direction, frightened=False, eaten=False,
               fright_flash=False):
    """Draw a ghost shape."""
    r = TILE // 2 - 2
    if eaten:
        # just eyes
        _draw_eyes(surf, cx, cy, direction, r)
        return

    body_col = colour
    if frightened:
        body_col = WHITE if fright_flash else FRIGHT_BLUE

    # body: semicircle top + rectangle + wavy bottom
    rect = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
    pygame.draw.circle(surf, body_col, (cx, cy - 1), r)
    pygame.draw.rect(surf, body_col, (cx - r, cy - 1, r * 2, r + 2))

    # wavy bottom
    wave_y = cy + r
    seg_w = (r * 2) // 3
    for i in range(3):
        sx = cx - r + i * seg_w
        points = [
            (sx, wave_y - 2),
            (sx + seg_w // 2, wave_y + 3),
            (sx + seg_w, wave_y - 2),
        ]
        pygame.draw.polygon(surf, body_col, points)

    if frightened:
        # simple face
        ey = cy - 2
        pygame.draw.circle(surf, WHITE if not fright_flash else FRIGHT_BLUE,
                           (cx - 3, ey), 2)
        pygame.draw.circle(surf, WHITE if not fright_flash else FRIGHT_BLUE,
                           (cx + 3, ey), 2)
        # wavy mouth
        my = cy + 3
        for i in range(5):
            mx = cx - 4 + i * 2
            mmy = my + (1 if i % 2 == 0 else -1)
            pygame.draw.circle(surf, WHITE if not fright_flash else FRIGHT_BLUE,
                               (mx, mmy), 1)
    else:
        _draw_eyes(surf, cx, cy, direction, r)


def _draw_eyes(surf, cx, cy, direction, r):
    """Draw ghost eyes looking in the given direction."""
    offsets = {Dir.LEFT: (-2, 0), Dir.RIGHT: (2, 0),
               Dir.UP: (0, -2), Dir.DOWN: (0, 2), Dir.NONE: (0, 0)}
    ox, oy = offsets[direction]
    for ex in (cx - 4, cx + 4):
        ey = cy - 2
        pygame.draw.ellipse(surf, WHITE, (ex - 3, ey - 3, 6, 7))
        pygame.draw.circle(surf, (33, 33, 200), (ex + ox, ey + oy + 1), 2)


def draw_cedar_tree(surf, cx, cy, h=60):
    """Draw a simple cedar tree (Lebanese symbol)."""
    trunk_w, trunk_h = 6, h // 5
    pygame.draw.rect(surf, (120, 80, 40),
                     (cx - trunk_w // 2, cy + h // 2 - trunk_h, trunk_w, trunk_h))
    layers = 4
    for i in range(layers):
        frac = 1 - i / (layers + 1)
        lw = int(h * 0.6 * frac)
        lh = h // (layers + 1)
        ly = cy - h // 2 + i * (lh * 2 // 3)
        points = [(cx, ly), (cx - lw // 2, ly + lh), (cx + lw // 2, ly + lh)]
        pygame.draw.polygon(surf, CEDAR, points)
        pygame.draw.polygon(surf, DARK_CEDAR, points, 1)


# =====================================================================
#  GHOST CLASS
# =====================================================================

class Ghost:
    def __init__(self, idx, name, colour, scatter_target, start, in_house):
        self.idx = idx
        self.name = name
        self.colour = colour
        self.scatter_target = scatter_target
        self.home_col, self.home_row = start
        self.in_house = in_house
        self.reset()

    def reset(self):
        self.col = self.home_col
        self.row = self.home_row
        self.px = self.col * TILE
        self.py = self.row * TILE
        self.direction = Dir.UP if not self.in_house else Dir.DOWN
        self.mode = GMode.SCATTER
        self.prev_mode = GMode.SCATTER
        self.in_house = (self.idx != 0)
        self.exiting = False
        self.released = (self.idx == 0)
        self.speed = GHOST_SPEED
        self.fright_flash = False

    @property
    def tile(self):
        return (self.px // TILE, self.py // TILE)

    def set_mode(self, mode):
        if self.mode == GMode.EATEN:
            return
        if mode == GMode.FRIGHT:
            if self.mode != GMode.EATEN:
                self.prev_mode = self.mode
                self.mode = GMode.FRIGHT
                self.direction = OPPOSITE[self.direction]
        else:
            self.prev_mode = mode
            if self.mode != GMode.FRIGHT and self.mode != GMode.EATEN:
                old = self.mode
                self.mode = mode
                if old != mode:
                    self.direction = OPPOSITE[self.direction]

    def get_speed(self):
        if self.mode == GMode.EATEN:
            return EATEN_SPEED
        if self.mode == GMode.FRIGHT:
            return FRIGHT_SPEED
        # slow in tunnel
        if self.row == 13 and (self.col < 6 or self.col > 21):
            return max(1, GHOST_SPEED - 1)
        return GHOST_SPEED

    def update(self, maze, player_tile, player_dir, red_ghost_tile):
        if self.in_house and not self.released:
            return
        if self.in_house and self.released and not self.exiting:
            self.exiting = True
            self.direction = Dir.UP

        spd = self.get_speed()
        grid = (self.px % TILE == 0 and self.py % TILE == 0)

        if grid:
            self.col = self.px // TILE
            self.row = self.py // TILE

            # Handle tunnel wrap
            if self.col < 0:
                self.col = COLS - 1
                self.px = self.col * TILE
            elif self.col >= COLS:
                self.col = 0
                self.px = 0

            # Arrived back at ghost house after being eaten
            if self.mode == GMode.EATEN and (self.col, self.row) == (13, 13):
                self.mode = self.prev_mode
                self.in_house = True
                self.exiting = True
                self.direction = Dir.UP

            # Exiting ghost house
            if self.exiting:
                if self.row <= 10 and self.col == 13:
                    self.in_house = False
                    self.exiting = False
                    self.direction = Dir.LEFT
                else:
                    # move toward exit: first go to col 13, then up
                    if self.col < 13:
                        self.direction = Dir.RIGHT
                    elif self.col > 13:
                        self.direction = Dir.LEFT
                    else:
                        self.direction = Dir.UP
            else:
                self._choose_direction(maze, player_tile, player_dir, red_ghost_tile)

        dx, dy = self.direction.value
        new_px = self.px + dx * spd
        new_py = self.py + dy * spd

        # tunnel wrap
        if new_px < -TILE:
            new_px = (COLS - 1) * TILE
        elif new_px >= COLS * TILE:
            new_px = 0

        self.px = new_px
        self.py = new_py

    def _choose_direction(self, maze, player_tile, player_dir, red_tile):
        target = self._get_target(player_tile, player_dir, red_tile)
        best_dir = Dir.NONE
        best_dist = float('inf')

        # Priority order: UP, LEFT, DOWN, RIGHT (classic Pac-Man)
        for d in (Dir.UP, Dir.LEFT, Dir.DOWN, Dir.RIGHT):
            if d == OPPOSITE[self.direction]:
                continue
            dx, dy = d.value
            nc = self.col + dx
            nr = self.row + dy
            t = tile_at(maze, nc, nr)

            can_walk = False
            if self.mode == GMode.EATEN:
                can_walk = walkable_ghost(t, eaten=True)
            else:
                can_walk = walkable_ghost(t)
                # prevent entering ghost house
                if t == R and self.mode != GMode.EATEN:
                    can_walk = False

            if can_walk:
                dd = dist_sq((nc % COLS, nr), target)
                if dd < best_dist:
                    best_dist = dd
                    best_dir = d

        if best_dir != Dir.NONE:
            self.direction = best_dir

    def _get_target(self, ptile, pdir, red_tile):
        if self.mode == GMode.SCATTER:
            return self.scatter_target
        if self.mode == GMode.FRIGHT:
            return (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
        if self.mode == GMode.EATEN:
            return (13, 13)
        # CHASE
        px, py = ptile
        dx, dy = pdir.value
        if self.idx == 0:  # Byblos – target player directly
            return ptile
        elif self.idx == 1:  # Sidon – 4 tiles ahead of player
            return (px + dx * 4, py + dy * 4)
        elif self.idx == 2:  # Tyre – double vector from red ghost to 2-ahead
            ax, ay = px + dx * 2, py + dy * 2
            rx, ry = red_tile
            return (ax + (ax - rx), ay + (ay - ry))
        else:  # Baalbek – chase if far, scatter if close
            if dist_sq(self.tile, ptile) > 64:
                return ptile
            return self.scatter_target

    def draw(self, surf, offset_y=0):
        cx = self.px + TILE // 2
        cy = self.py + TILE // 2 + offset_y
        draw_ghost(surf, cx, cy, self.colour, self.direction,
                   frightened=(self.mode == GMode.FRIGHT),
                   eaten=(self.mode == GMode.EATEN),
                   fright_flash=self.fright_flash)


# =====================================================================
#  GAME
# =====================================================================

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Lebanese Ms. Pac-Man  |  Yalla!")
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.SysFont("arial", 36, bold=True)
        self.font_med = pygame.font.SysFont("arial", 22, bold=True)
        self.font_sm = pygame.font.SysFont("arial", 16)
        self.state = State.TITLE
        self.high_score = 0
        self._new_game()

    # ---- initialisation ----
    def _new_game(self):
        self.maze = deepcopy(MAZE_TEMPLATE)
        self.score = 0
        self.lives = LIVES
        self.level = 1
        self.dots_left = sum(t in (D, P) for row in self.maze for t in row)
        self.total_dots = self.dots_left
        self._init_entities()
        self.mode_idx = 0
        self.mode_timer = SCATTER_DUR[0]
        self.global_mode = GMode.SCATTER
        self.fright_timer = 0
        self.ghost_eat_combo = 0
        self.bonus_shown = False
        self.bonus_timer = 0
        self.bonus_pos = None
        self.bonus_idx = min(self.level - 1, len(BONUS_FOODS) - 1)
        self.score_popups = []
        self.release_timer = 0
        self.released_count = 1
        self.frame = 0

    def _init_entities(self):
        # player
        self.p_col, self.p_row = PLAYER_START
        self.p_px = self.p_col * TILE
        self.p_py = self.p_row * TILE
        self.p_dir = Dir.LEFT
        self.p_next = Dir.NONE
        self.p_anim = 0
        self.p_mouth = 0.0
        self.p_moving = False
        self.death_frame = 0

        # ghosts
        self.ghosts = []
        for i, (name, col, sc, start, inh) in enumerate(GHOST_DEFS):
            self.ghosts.append(Ghost(i, name, col, sc, start, inh))

    def _reset_positions(self):
        self.p_col, self.p_row = PLAYER_START
        self.p_px = self.p_col * TILE
        self.p_py = self.p_row * TILE
        self.p_dir = Dir.LEFT
        self.p_next = Dir.NONE
        self.p_moving = False
        for g in self.ghosts:
            g.reset()
        self.fright_timer = 0
        self.ghost_eat_combo = 0
        self.global_mode = GMode.SCATTER
        self.mode_idx = 0
        self.mode_timer = SCATTER_DUR[0]
        self.release_timer = 0
        self.released_count = 1

    def _next_level(self):
        self.level += 1
        self.maze = deepcopy(MAZE_TEMPLATE)
        self.dots_left = sum(t in (D, P) for row in self.maze for t in row)
        self.total_dots = self.dots_left
        self._reset_positions()
        self.bonus_shown = False
        self.bonus_timer = 0
        self.bonus_pos = None
        self.bonus_idx = min(self.level - 1, len(BONUS_FOODS) - 1)
        self.score_popups = []

    # ---- main loop ----
    def run(self):
        while True:
            self._handle_events()
            self._update()
            self._draw()
            self.clock.tick(FPS)

    # ---- events ----
    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if self.state == State.TITLE:
                    if ev.key == pygame.K_RETURN:
                        self._new_game()
                        self.state = State.READY
                        self.ready_timer = READY_DUR
                elif self.state == State.GAMEOVER:
                    if ev.key == pygame.K_RETURN:
                        self.state = State.TITLE
                elif self.state == State.PLAYING:
                    if ev.key == pygame.K_UP:
                        self.p_next = Dir.UP
                    elif ev.key == pygame.K_DOWN:
                        self.p_next = Dir.DOWN
                    elif ev.key == pygame.K_LEFT:
                        self.p_next = Dir.LEFT
                    elif ev.key == pygame.K_RIGHT:
                        self.p_next = Dir.RIGHT

    # ---- update ----
    def _update(self):
        self.frame += 1

        if self.state == State.READY:
            self.ready_timer -= 1
            if self.ready_timer <= 0:
                self.state = State.PLAYING
            return

        if self.state == State.DYING:
            self.death_frame += 1
            if self.death_frame >= DEATH_DUR:
                self.lives -= 1
                if self.lives <= 0:
                    self.high_score = max(self.high_score, self.score)
                    self.state = State.GAMEOVER
                else:
                    self._reset_positions()
                    self.state = State.READY
                    self.ready_timer = READY_DUR
            return

        if self.state == State.LEVELUP:
            self.death_frame += 1
            if self.death_frame >= LEVEL_DUR:
                self._next_level()
                self.state = State.READY
                self.ready_timer = READY_DUR
            return

        if self.state != State.PLAYING:
            return

        # --- ghost release ---
        self.release_timer += 1
        if self.release_timer >= RELEASE_INTERVAL and self.released_count < 4:
            self.release_timer = 0
            self.released_count += 1
            for g in self.ghosts:
                if not g.released:
                    g.released = True
                    break

        # --- mode cycling ---
        if self.fright_timer > 0:
            self.fright_timer -= 1
            flash = self.fright_timer < FRIGHT_WARN and (self.fright_timer // 10) % 2 == 0
            for g in self.ghosts:
                g.fright_flash = flash
            if self.fright_timer <= 0:
                for g in self.ghosts:
                    if g.mode == GMode.FRIGHT:
                        g.mode = g.prev_mode
                    g.fright_flash = False
                self.ghost_eat_combo = 0
        else:
            if self.mode_timer is not None:
                self.mode_timer -= 1
                if self.mode_timer <= 0:
                    if self.global_mode == GMode.SCATTER:
                        self.global_mode = GMode.CHASE
                        dur = CHASE_DUR[min(self.mode_idx, len(CHASE_DUR) - 1)]
                    else:
                        self.mode_idx += 1
                        self.global_mode = GMode.SCATTER
                        dur = SCATTER_DUR[min(self.mode_idx, len(SCATTER_DUR) - 1)]
                    self.mode_timer = dur
                    for g in self.ghosts:
                        g.set_mode(self.global_mode)

        # --- player movement ---
        self._move_player()

        # --- ghost movement ---
        red_tile = self.ghosts[0].tile
        ptile = (self.p_col, self.p_row)
        for g in self.ghosts:
            g.update(self.maze, ptile, self.p_dir, red_tile)

        # --- eating dots ---
        grid = (self.p_px % TILE == 0 and self.p_py % TILE == 0)
        if grid:
            self.p_col = self.p_px // TILE
            self.p_row = self.p_py // TILE
            t = tile_at(self.maze, self.p_col, self.p_row)
            if t == D:
                self.maze[self.p_row][self.p_col] = E
                self.score += DOT_PTS
                self.dots_left -= 1
            elif t == P:
                self.maze[self.p_row][self.p_col] = E
                self.score += POWER_PTS
                self.dots_left -= 1
                self.fright_timer = FRIGHT_DUR
                self.ghost_eat_combo = 0
                for g in self.ghosts:
                    g.set_mode(GMode.FRIGHT)

        # --- bonus fruit ---
        if not self.bonus_shown and self.dots_left <= self.total_dots // 2:
            self.bonus_shown = True
            self.bonus_timer = 10 * FPS
            self.bonus_pos = (14, 16)
        if self.bonus_pos:
            self.bonus_timer -= 1
            if self.bonus_timer <= 0:
                self.bonus_pos = None
            elif (self.p_col, self.p_row) == self.bonus_pos:
                pts = BONUS_SCORES[self.bonus_idx]
                self.score += pts
                self.score_popups.append((self.bonus_pos, str(pts), 60))
                self.bonus_pos = None

        # --- collisions ---
        for g in self.ghosts:
            if g.mode == GMode.EATEN or g.in_house:
                continue
            if abs(self.p_px - g.px) < TILE * 0.7 and abs(self.p_py - g.py) < TILE * 0.7:
                if g.mode == GMode.FRIGHT:
                    g.mode = GMode.EATEN
                    pts = GHOST_PTS[min(self.ghost_eat_combo, 3)]
                    self.ghost_eat_combo += 1
                    self.score += pts
                    self.score_popups.append((g.tile, str(pts), 45))
                else:
                    self.state = State.DYING
                    self.death_frame = 0
                    return

        # --- level complete ---
        if self.dots_left <= 0:
            self.state = State.LEVELUP
            self.death_frame = 0

        # --- score popups decay ---
        self.score_popups = [(p, t, f - 1) for p, t, f in self.score_popups if f > 1]

        # --- player animation ---
        if self.p_moving:
            self.p_anim += 1
            self.p_mouth = abs(math.sin(self.p_anim * 0.3)) * 45
        else:
            self.p_mouth = 10

    def _move_player(self):
        grid = (self.p_px % TILE == 0 and self.p_py % TILE == 0)
        if grid:
            self.p_col = self.p_px // TILE
            self.p_row = self.p_py // TILE

            # tunnel wrap
            if self.p_col < 0:
                self.p_col = COLS - 1
                self.p_px = self.p_col * TILE
            elif self.p_col >= COLS:
                self.p_col = 0
                self.p_px = 0

            # try buffered direction
            if self.p_next != Dir.NONE:
                dx, dy = self.p_next.value
                nc, nr = self.p_col + dx, self.p_row + dy
                if walkable_player(tile_at(self.maze, nc, nr)):
                    self.p_dir = self.p_next

            # check if current direction is valid
            dx, dy = self.p_dir.value
            nc, nr = self.p_col + dx, self.p_row + dy
            if not walkable_player(tile_at(self.maze, nc, nr)):
                self.p_moving = False
                return

        self.p_moving = True
        dx, dy = self.p_dir.value
        self.p_px += dx * PLAYER_SPEED
        self.p_py += dy * PLAYER_SPEED

        # tunnel wrap pixel
        if self.p_px < -TILE:
            self.p_px = (COLS - 1) * TILE
        elif self.p_px >= COLS * TILE:
            self.p_px = 0

    # ---- drawing ----
    def _draw(self):
        self.screen.fill(BG)

        if self.state == State.TITLE:
            self._draw_title()
        elif self.state == State.GAMEOVER:
            self._draw_gameover()
        else:
            self._draw_maze()
            if self.state == State.PLAYING or self.state == State.READY:
                self._draw_entities()
            elif self.state == State.DYING:
                self._draw_death()
            elif self.state == State.LEVELUP:
                self._draw_level_complete()
            self._draw_hud()

        pygame.display.flip()

    def _draw_maze(self):
        oy = HUD_H
        for r in range(ROWS):
            for c in range(COLS):
                t = self.maze[r][c]
                x = c * TILE
                y = r * TILE + oy
                if t == W:
                    pygame.draw.rect(self.screen, CEDAR, (x + 1, y + 1, TILE - 2, TILE - 2))
                    pygame.draw.rect(self.screen, DARK_CEDAR, (x + 1, y + 1, TILE - 2, TILE - 2), 1)
                elif t == D:
                    # hummus dot
                    pygame.draw.circle(self.screen, HUMMUS,
                                       (x + TILE // 2, y + TILE // 2), 3)
                elif t == P:
                    # manoushe power pellet (pulsing)
                    pulse = 4 + int(2 * abs(math.sin(self.frame * 0.08)))
                    pygame.draw.circle(self.screen, MANOUSHE,
                                       (x + TILE // 2, y + TILE // 2), pulse)
                    pygame.draw.circle(self.screen, (220, 160, 80),
                                       (x + TILE // 2, y + TILE // 2), pulse, 1)
                elif t == R:
                    pygame.draw.rect(self.screen, DOOR_COL, (x, y + TILE // 2 - 2, TILE, 4))

        # bonus item
        if self.bonus_pos and self.state == State.PLAYING:
            bx = self.bonus_pos[0] * TILE + TILE // 2
            by = self.bonus_pos[1] * TILE + TILE // 2 + oy
            self._draw_bonus(bx, by, self.bonus_idx)

    def _draw_bonus(self, cx, cy, idx):
        """Draw a Lebanese food bonus item."""
        if idx == 0:  # Falafel - green circle
            pygame.draw.circle(self.screen, (120, 160, 60), (cx, cy), 8)
            pygame.draw.circle(self.screen, (90, 130, 40), (cx, cy), 8, 1)
        elif idx == 1:  # Shawarma - brown wrap shape
            pygame.draw.ellipse(self.screen, (180, 130, 70), (cx - 8, cy - 6, 16, 12))
            pygame.draw.ellipse(self.screen, (150, 100, 50), (cx - 8, cy - 6, 16, 12), 1)
        elif idx == 2:  # Kibbeh - dark oval
            pygame.draw.ellipse(self.screen, (140, 80, 40), (cx - 7, cy - 5, 14, 10))
            pygame.draw.ellipse(self.screen, (100, 60, 30), (cx - 7, cy - 5, 14, 10), 1)
        elif idx == 3:  # Baklava - golden diamond
            pts = [(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)]
            pygame.draw.polygon(self.screen, (200, 170, 60), pts)
            pygame.draw.polygon(self.screen, (170, 140, 40), pts, 1)
        else:  # Cedar tree
            draw_cedar_tree(self.screen, cx, cy, 20)

    def _draw_entities(self):
        oy = HUD_H
        # ghosts
        for g in self.ghosts:
            g.draw(self.screen, oy)
        # player
        cx = self.p_px + TILE // 2
        cy = self.p_py + TILE // 2 + oy
        draw_pacman(self.screen, cx, cy, self.p_dir, self.p_mouth)

        # score popups
        for (pc, pr), txt, fr in self.score_popups:
            alpha = min(255, fr * 6)
            popup = self.font_sm.render(txt, True, WHITE)
            popup.set_alpha(alpha)
            self.screen.blit(popup, (pc * TILE, pr * TILE + oy - (45 - fr)))

        # ready text
        if self.state == State.READY:
            txt = self.font_big.render("!يلّا", True, YELLOW)
            rect = txt.get_rect(center=(WIDTH // 2, ROWS * TILE // 2 + oy))
            self.screen.blit(txt, rect)

    def _draw_death(self):
        oy = HUD_H
        # shrinking pac-man
        progress = self.death_frame / DEATH_DUR
        size = max(2, int((TILE - 4) * (1 - progress)))
        cx = self.p_px + TILE // 2
        cy = self.p_py + TILE // 2 + oy
        mouth = progress * 180
        draw_pacman(self.screen, cx, cy, Dir.UP, mouth, size)

    def _draw_level_complete(self):
        oy = HUD_H
        # flash maze walls
        flash = (self.death_frame // 8) % 2 == 0
        for r in range(ROWS):
            for c in range(COLS):
                if self.maze[r][c] == W:
                    x = c * TILE
                    y = r * TILE + oy
                    col = WHITE if flash else CEDAR
                    pygame.draw.rect(self.screen, col, (x + 1, y + 1, TILE - 2, TILE - 2))
        # player stays visible
        cx = self.p_px + TILE // 2
        cy = self.p_py + TILE // 2 + oy
        draw_pacman(self.screen, cx, cy, self.p_dir, 10)

    def _draw_hud(self):
        # score
        score_txt = self.font_med.render(f"Score: {self.score}", True, WHITE)
        self.screen.blit(score_txt, (10, 10))

        # high score
        hs = max(self.high_score, self.score)
        hs_txt = self.font_sm.render(f"High: {hs}", True, (180, 180, 180))
        self.screen.blit(hs_txt, (WIDTH // 2 - hs_txt.get_width() // 2, 14))

        # level
        lvl_txt = self.font_med.render(f"Level {self.level}", True, CEDAR)
        self.screen.blit(lvl_txt, (WIDTH - lvl_txt.get_width() - 10, 10))

        # lives
        for i in range(self.lives):
            cx = 20 + i * 28
            cy = 55
            draw_pacman(self.screen, cx, cy, Dir.RIGHT, 30, 16)

        # ghost names and bonus item display
        bx = WIDTH - 30
        for i in range(min(self.level, len(BONUS_FOODS))):
            self._draw_bonus(bx, 55, i)
            bx -= 28

    def _draw_title(self):
        # background cedar tree
        draw_cedar_tree(self.screen, WIDTH // 2, HEIGHT // 2 + 30, 120)

        # Lebanese flag stripe at top
        stripe_h = 8
        pygame.draw.rect(self.screen, LEB_RED, (0, 0, WIDTH, stripe_h))
        pygame.draw.rect(self.screen, WHITE, (0, stripe_h, WIDTH, stripe_h))
        pygame.draw.rect(self.screen, CEDAR, (0, stripe_h * 2, WIDTH, stripe_h))

        # title
        t1 = self.font_big.render("LEBANESE", True, CEDAR)
        t2 = self.font_big.render("MS. PAC-MAN", True, YELLOW)
        self.screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, 80))
        self.screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, 125))

        # subtitle
        sub = self.font_med.render("Eat hummus, avoid ghosts, collect falafel!", True, WHITE)
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, 190))

        # ghost names
        y = 250
        for name, col, _, _, _ in GHOST_DEFS:
            ghost_label = self.font_sm.render(f"- {name}", True, col)
            self.screen.blit(ghost_label, (WIDTH // 2 - 60, y))
            y += 24

        # controls
        ctrl = self.font_sm.render("Arrow keys to move | ESC to quit", True, (150, 150, 150))
        self.screen.blit(ctrl, (WIDTH // 2 - ctrl.get_width() // 2, HEIGHT - 120))

        # start prompt
        if (self.frame // 30) % 2 == 0:
            start = self.font_med.render("Press ENTER to start", True, WHITE)
            self.screen.blit(start, (WIDTH // 2 - start.get_width() // 2, HEIGHT - 70))

        # high score
        if self.high_score > 0:
            hs = self.font_sm.render(f"High Score: {self.high_score}", True, YELLOW)
            self.screen.blit(hs, (WIDTH // 2 - hs.get_width() // 2, HEIGHT - 40))

    def _draw_gameover(self):
        self._draw_maze()

        # overlay
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        t1 = self.font_big.render("GAME OVER", True, LEB_RED)
        self.screen.blit(t1, (WIDTH // 2 - t1.get_width() // 2, HEIGHT // 2 - 80))

        t2 = self.font_med.render("!معلش", True, WHITE)
        self.screen.blit(t2, (WIDTH // 2 - t2.get_width() // 2, HEIGHT // 2 - 30))

        sc = self.font_med.render(f"Final Score: {self.score}", True, YELLOW)
        self.screen.blit(sc, (WIDTH // 2 - sc.get_width() // 2, HEIGHT // 2 + 20))

        if (self.frame // 30) % 2 == 0:
            r = self.font_sm.render("Press ENTER to continue", True, (200, 200, 200))
            self.screen.blit(r, (WIDTH // 2 - r.get_width() // 2, HEIGHT // 2 + 70))

        self._draw_hud()


# =====================================================================
#  ENTRY POINT
# =====================================================================

def main():
    game = Game()
    game.run()

if __name__ == "__main__":
    main()
