# ==============================================================================
# Playing With Fire 2 — Build & Run Makefile
# ==============================================================================

# Automatically prefer the project virtualenv Python if it exists
ifneq ($(wildcard ./venv/bin/python),)
    PYTHON ?= ./venv/bin/python
else
    PYTHON ?= python3
endif

CXX      ?= g++
CXXFLAGS ?= -O3 -Wall -std=c++17 -fPIC -Iinclude -MMD -MP

# Query pybind11 include flags and extension suffix from the active Python
PYBIND_INCLUDES := $(shell $(PYTHON) -m pybind11 --includes)
EXT_SUFFIX      := $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')")

TARGET_SO  := bomberman_engine$(EXT_SUFFIX)
TARGET_BIN := bomberman
BUILD_DIR  := build

# Shared C++ engine sources (used by both Python extension and console binary)
ENGINE_SRCS := \
	src/core/Board.cpp \
	src/core/ConsoleInput.cpp \
	src/core/ConsoleRenderer.cpp \
	src/core/Game.cpp \
	src/core/World.cpp \
	src/entities/Entity.cpp \
	src/entities/Player.cpp \
	src/entities/Bomb.cpp \
	src/entities/Flame.cpp \
	src/entities/BreakableWall.cpp \
	src/entities/DumbBot.cpp \
	src/entities/PowerUp.cpp \
	src/entities/BombPowerUp.cpp \
	src/entities/LightningPowerUp.cpp \
	src/entities/SpeedPowerUp.cpp \
	src/entities/HammerPowerUp.cpp \
	src/entities/RingPowerUp.cpp \
	src/factories/PowerUpFactory.cpp \
	src/levels/ClassicLevel.cpp \
	src/systems/CollisionSystem.cpp \
	src/systems/ExplosionSystem.cpp \
	src/systems/SuddenDeathSystem.cpp

BINDING_SRC := src/bindings/bindings.cpp
MAIN_SRC    := src/main.cpp

ENGINE_OBJS  := $(patsubst src/%.cpp,$(BUILD_DIR)/%.o,$(ENGINE_SRCS))
BINDING_OBJ  := $(patsubst src/%.cpp,$(BUILD_DIR)/%.o,$(BINDING_SRC))
MAIN_OBJ     := $(patsubst src/%.cpp,$(BUILD_DIR)/%.o,$(MAIN_SRC))

ALL_DEPS := $(ENGINE_OBJS:.o=.d) $(BINDING_OBJ:.o=.d) $(MAIN_OBJ:.o=.d)

.PHONY: all build run play duel test train console clean rebuild help

# Default target: build the C++ Pybind11 engine module
all: build

build: $(TARGET_SO)

# Link the shared library for Python (bomberman_engine*.so)
$(TARGET_SO): $(ENGINE_OBJS) $(BINDING_OBJ)
	@echo "[Link] Creating Python C++ extension: $@"
	$(CXX) $(CXXFLAGS) -shared $^ -o $@
	@echo "[Done] Build complete: $@"

# Compile C++ engine object files
$(BUILD_DIR)/%.o: src/%.cpp
	@mkdir -p $(dir $@)
	@echo "[CXX]  $<"
	$(CXX) $(CXXFLAGS) $(PYBIND_INCLUDES) -c $< -o $@

# Build (if needed) and launch the Pygame GUI (starts in Main Menu)
run: $(TARGET_SO)
	$(PYTHON) play_gui.py

play: run

# Launch Pygame GUI directly in 1v1 AI Duel mode: v8 (Masked PPO) vs v7 (Grandmaster)
duel: $(TARGET_SO)
	$(PYTHON) play_gui.py --duel

# Build (if needed) and run the test suite
test: $(TARGET_SO)
	$(PYTHON) -m unittest discover -s tests -v

# Build (if needed) and run PPO RL training
train: $(TARGET_SO)
	$(PYTHON) train.py

# Build standalone terminal/console C++ executable
console: $(TARGET_BIN)

$(TARGET_BIN): $(ENGINE_OBJS) $(MAIN_OBJ)
	@echo "[Link] Creating console executable: $@"
	$(CXX) $(CXXFLAGS) $^ -o $@
	@echo "[Done] Run with ./$(TARGET_BIN)"

# Remove all build artifacts
clean:
	@echo "[Clean] Removing build artifacts..."
	rm -rf $(BUILD_DIR) *.o $(TARGET_BIN) bomberman_engine*.so
	find . -maxdepth 2 -name "__pycache__" -type d -exec rm -rf {} +

# Full clean + parallel rebuild
rebuild: clean
	$(MAKE) all

help:
	@echo "=================================================================="
	@echo " Playing With Fire 2 — Makefile Commands"
	@echo "=================================================================="
	@echo "  make           Compile the C++ engine module (incremental)"
	@echo "  make -j        Compile in parallel using all CPU cores"
	@echo "  make run       Compile (if needed) and launch the Pygame GUI"
	@echo "  make test      Compile (if needed) and run unit tests"
	@echo "  make train     Compile (if needed) and start RL training"
	@echo "  make console   Compile the standalone C++ terminal binary"
	@echo "  make clean     Remove all compiled object files and .so binaries"
	@echo "  make rebuild   Clean and recompile everything from scratch"
	@echo "=================================================================="

-include $(ALL_DEPS)
