#!/bin/bash
set -e

error() {
  echo "Error: $@" >&2
  exit 1
}

# Parse arguments
BLOATED=0
INCLUDES=()

for arg in "$@"; do
  case "$arg" in
    --bloated) BLOATED=1 ;;
    --include=*) INCLUDES+=("${arg#--include=}") ;;
  esac
done

# Save where we started
export LAST_CWD=$(pwd)

# Prepare VFS directory
cd "$PREFIX/tmp" || error "no such dir: $PREFIX/tmp"
rm -rf txtosvfs_*       # clean up any existing VFS
TXTOS_DIR=$(mktemp -d txtosvfs_XXXXXX) || error "failed to create VFS dir"
echo "✅ Created new VFS at $TXTOS_DIR"

# Prepare directories
mkdir -p "$TXTOS_DIR/lib" "$TXTOS_DIR/system" "$TXTOS_DIR/bin" "$TXTOS_DIR/etc" "$TXTOS_DIR/root"

# ✅ Copy base shell & linker
cp -u /bin/sh "$TXTOS_DIR/bin"
cp -u /bin/linker64 "$TXTOS_DIR/bin"
cp -u /bin/linker64 "$TXTOS_DIR/lib"

# ✅ Copy all system libraries and follow symlinks so we never copy a dead link
# Copy minimal set of system libraries
echo "Copying minimal system libraries..."

cp -L /system/lib64/libc.so         "$TXTOS_DIR/lib"
cp -L /system/lib64/libm.so         "$TXTOS_DIR/lib"
cp -L /system/lib64/libdl.so        "$TXTOS_DIR/lib"
cp -L /system/lib64/liblog.so       "$TXTOS_DIR/lib"
cp -L /system/lib64/libandroid.so   "$TXTOS_DIR/lib"
cp -L /system/lib64/libcutils.so    "$TXTOS_DIR/lib"
cp -L /system/lib64/libutils.so     "$TXTOS_DIR/lib"
cp -L /system/lib64/libstdc++.so    "$TXTOS_DIR/lib"
cp -L /system/lib64/libz.so         "$TXTOS_DIR/lib"
cp -L /system/lib64/libcrypto.so    "$TXTOS_DIR/lib"
cp -L /system/lib64/libssl.so       "$TXTOS_DIR/lib"
cp -L /system/lib64/libsqlite.so    "$TXTOS_DIR/lib"

# (Copy into system/lib & system/lib64 too)
rm -rf "$TXTOS_DIR/system/lib" "$TXTOS_DIR/system/lib64"
cp -r "$TXTOS_DIR/lib" "$TXTOS_DIR/system/lib"
cp -r "$TXTOS_DIR/lib" "$TXTOS_DIR/system/lib64"

# ✅ Gather any extra apex libs too
echo "Scanning apex libs..."
strace -f proot -r "$TXTOS_DIR" --bind=/dev --bind=/proc /bin/sh 2> log.txt || true
grep -oE '"/apex[^"]+"' log.txt | tr -d '"' | sort -u | while read path; do
  if [ -e "$path" ]; then cp -ruL --parents "$path" "$TXTOS_DIR" || true; fi
done

# ✅ Fetch busybox
BUSYBOX_PATH="$TXTOS_DIR/bin/busybox"
wget -q https://github.com/Magisk-Modules-Repo/busybox-ndk/raw/refs/heads/master/busybox-arm64 -O "$BUSYBOX_PATH"
chmod +x "$BUSYBOX_PATH"
echo "Installing busybox applets into $TXTOS_DIR/bin"
for applet in $("$BUSYBOX_PATH" --list); do
  ln -sf "busybox" "$TXTOS_DIR/bin/$applet"
done

# ✅ Bloated binaries if requested
if [ $BLOATED -eq 1 ]; then
  BASE_URL="https://api.github.com/repos/polaco1782/linux-static-binaries/contents/armv8-aarch64"
  echo "Fetching file list from $BASE_URL..."
  ALL_FILES=$(curl -s $BASE_URL | grep '"download_url"' | cut -d '"' -f 4 | sed 's#.*/##')
  BUSYBOX_APPLETS=$("$BUSYBOX_PATH" --list)
  NEEDED=$(comm -23 <(echo "$ALL_FILES" | sort) <(echo "$BUSYBOX_APPLETS" | sort))
  for bin in $NEEDED; do
    wget -q "https://github.com/polaco1782/linux-static-binaries/raw/master/armv8-aarch64/$bin" -P "$TXTOS_DIR/bin/"
    chmod +x "$TXTOS_DIR/bin/$bin"
    echo "installed $bin"
  done
fi

# ✅ Fetch individually requested binaries
for bin in "${INCLUDES[@]}"; do
  wget -q "https://github.com/polaco1782/linux-static-binaries/raw/master/armv8-aarch64/$bin" -P "$TXTOS_DIR/bin/"
  chmod +x "$TXTOS_DIR/bin/$bin"
  echo "installed requested $bin"
done

# ✅ etc files
echo 'root:x:0:0:root:/root:/bin/sh' > "$TXTOS_DIR/etc/passwd"
echo 'root:x:0:' > "$TXTOS_DIR/etc/group"
echo 'root:$6$KRQ.XVFSWRQaZdsd$m5FKXTRFF6I94iCeGnDp1VBf0dL.4RM4Otgd1AnYgQaiqHHT5BBD9303vW13Nqnwfcy6dUogwLm5EbLq0DLOw/:19000:0:99999:7:::' > "$TXTOS_DIR/etc/shadow"
chmod 600 "$TXTOS_DIR/etc/shadow"
chmod 644 "$TXTOS_DIR/etc/passwd" "$TXTOS_DIR/etc/group"

# ✅ linkerconfig & zoneinfo
mkdir -p "$TXTOS_DIR/linkerconfig"
touch "$TXTOS_DIR/linkerconfig/ld.config.txt"
mkdir -p "$TXTOS_DIR/system/usr/share/zoneinfo"
cp -r /system/usr/share/zoneinfo "$TXTOS_DIR/system/usr/share/zoneinfo"

# give a simple nano alternative since thats broken in static builds
cat > "$TXTOS_DIR/bin/nano" <<'EOF'
#!/bin/sh

FILE="$1"
if [ -z "$FILE" ]; then
  echo "Usage: $0 <filename>"
  exit 1
fi

echo "Enter your text. Put a single '.' on its own line to finish:"
# Truncate the file if it exists
: > "$FILE"
while IFS= read -r line; do
  if [ "$line" = "." ]; then
    break
  fi
  echo "$line" >> "$FILE"
done
echo "✅ Wrote to $FILE"
EOF

chmod +x "$TXTOS_DIR/bin/nano"

# ✅ Startup script
RUN_SCRIPT="$LAST_CWD/startup.sh"
cwd=$(pwd)
echo "env -i $(which proot) -0 -r $cwd/$TXTOS_DIR -b /dev -b /proc -w / /bin/sh -c 'export PATH=/bin; export HOME=/root; export LD_LIBRARY_PATH=/lib:/system/lib64; exec /bin/sh'" > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"
echo "✅ Done — startup script created at $RUN_SCRIPT"
