#!/usr/bin/env bash
# Rebuild whisper.cpp and llama.cpp with Vulkan (AMD iGPU / dGPU) support
# and install them into the voxd bin directory.
#
# Prerequisites are installed automatically (apt/dnf/pacman).
# Original CPU binaries are backed up as *.cpu.bak.
set -euo pipefail

VOXD_BIN_DIR="${HOME}/.local/share/voxd/bin"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# --- package manager detection ---
install_pkg() {
  if command -v apt-get >/dev/null; then
    sudo apt-get install -y "$@"
  elif command -v dnf >/dev/null; then
    sudo dnf install -y "$@"
  elif command -v pacman >/dev/null; then
    sudo pacman -S --noconfirm "$@"
  else
    echo "Unsupported package manager. Install manually: $*" >&2
    exit 1
  fi
}

# --- install Vulkan dev deps ---
echo "==> Checking Vulkan dependencies..."
NEEDED=()
for cmd in vulkaninfo glslc; do
  command -v "$cmd" >/dev/null || NEEDED+=("$cmd")
done
pkg-config --exists vulkan 2>/dev/null || NEEDED+=(libvulkan-dev)

if [[ ${#NEEDED[@]} -gt 0 ]]; then
  echo "==> Installing: ${NEEDED[*]}"
  PKGS=()
  for n in "${NEEDED[@]}"; do
    case "$n" in
      vulkaninfo)    PKGS+=(vulkan-tools) ;;
      glslc)         PKGS+=(glslc) ;;
      libvulkan-dev) PKGS+=(libvulkan-dev) ;;
    esac
  done
  install_pkg "${PKGS[@]}"
fi

# --- verify GPU is visible ---
echo "==> Verifying Vulkan GPU..."
if ! vulkaninfo --summary 2>&1 | grep -qi "INTEGRATED_GPU\|DISCRETE_GPU"; then
  echo "ERROR: No Vulkan GPU detected. Check your drivers." >&2
  exit 1
fi
vulkaninfo --summary 2>&1 | grep "deviceName" | head -1

# --- build whisper.cpp ---
echo "==> Cloning whisper.cpp..."
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$WORK_DIR/whisper.cpp"

echo "==> Building whisper.cpp with Vulkan..."
cmake -S "$WORK_DIR/whisper.cpp" -B "$WORK_DIR/whisper.cpp/build" \
  -DBUILD_SHARED_LIBS=OFF -DGGML_VULKAN=ON
cmake --build "$WORK_DIR/whisper.cpp/build" -j"$(nproc)"

# --- build llama.cpp ---
echo "==> Cloning llama.cpp..."
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$WORK_DIR/llama.cpp"

echo "==> Building llama.cpp with Vulkan..."
cmake -S "$WORK_DIR/llama.cpp" -B "$WORK_DIR/llama.cpp/build" \
  -DBUILD_SHARED_LIBS=OFF -DGGML_VULKAN=ON -DLLAMA_CURL=ON
cmake --build "$WORK_DIR/llama.cpp/build" -j"$(nproc)" --target llama-server

# --- install ---
mkdir -p "$VOXD_BIN_DIR"

for bin in whisper-cli llama-server; do
  if [[ "$bin" == "whisper-cli" ]]; then
    src="$WORK_DIR/whisper.cpp/build/bin/$bin"
  else
    src="$WORK_DIR/llama.cpp/build/bin/$bin"
  fi

  # backup existing
  if [[ -f "$VOXD_BIN_DIR/$bin" ]]; then
    cp "$VOXD_BIN_DIR/$bin" "$VOXD_BIN_DIR/${bin}.cpu.bak"
    echo "    Backed up $bin -> ${bin}.cpu.bak"
  fi

  cp "$src" "$VOXD_BIN_DIR/$bin"
  chmod +x "$VOXD_BIN_DIR/$bin"
  echo "    Installed $bin (Vulkan)"
done

# --- verify ---
echo ""
echo "==> Verifying Vulkan linkage..."
for bin in whisper-cli llama-server; do
  if ldd "$VOXD_BIN_DIR/$bin" | grep -q libvulkan; then
    echo "    $bin: Vulkan OK"
  else
    echo "    $bin: WARNING - libvulkan not linked!" >&2
  fi
done

echo ""
echo "Done. Restart voxd to use GPU-accelerated binaries."
