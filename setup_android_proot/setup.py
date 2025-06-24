#!/bin/bash
set -e

error() {
  echo "Error: $@" >&2
  exit 1
}

# Save where we started
export LAST_CWD=$(pwd)

# Create temp dir
GO=$(mktemp -d) || error "failed to create temp dir"
cd "$GO/.." || error "failed to cd to parent of temp dir"
rm -rf "$GO"

# Enter TMP so our VFS will live there
cd "$PREFIX/tmp" || error "no such dir: $PREFIX/tmp"

# Find txtosvfs directory
TXTOS_DIR=$(find . -maxdepth 1 -type d -name "txtosvfs_*" | head -n1)
if [ -z "$TXTOS_DIR" ]; then
  error "no txtosvfs_* directory found — did you run os.py first?"
fi

# Prepare directories
mkdir -p "$TXTOS_DIR/lib" "$TXTOS_DIR/system" "$TXTOS_DIR/bin" || error "failed to prepare directories"

# Copy base sh and linker
ldd /bin/sh | awk '{print $3}' | xargs -I {} cp -u {} "$TXTOS_DIR/system/lib64"
cp -u /bin/sh "$TXTOS_DIR/bin"
cp -u /bin/linker64 "$TXTOS_DIR/bin"
cp -u "$TXTOS_DIR/bin/linker64" "$TXTOS_DIR/lib"
cp -ru "$TXTOS_DIR/bin" "$TXTOS_DIR/system"
cp -ru "$TXTOS_DIR/lib" "$TXTOS_DIR/system"
# Gather libs that arent needed but recommended
# Common Bionic loader and C library

cd $TXTOS_DIR/lib
cp /apex/com.android.runtime/lib64/bionic/libc.so ./
cp /system/lib64/libm.so ./
cp /system/lib64/libdl.so ./
cp /system/lib64/liblog.so ./
cp /system/lib64/libstdc++.so ./
cp /system/lib64/libz.so ./
cp /system/lib64/libandroid.so ./       # Android-specific
cp /system/lib64/libbinder.so ./        # Binder client
cp /system/lib64/libutils.so ./         # Android utils
cp /system/lib64/libcutils.so ./        # Common utils
cp /system/lib64/libcrypto.so ./        # OpenSSL (if present)
cp /system/lib64/libssl.so ./           # OpenSSL (if present)
cp /system/lib64/libsqlite.so ./        # SQLite (if present)
cd ../..

# Gather apex libs
echo "Scanning apex libs..."
strace -f proot -r "$TXTOS_DIR" --bind=/dev --bind=/proc /bin/sh 2> log.txt || true
grep -oE '"/apex[^"]+"' log.txt | tr -d '"' | sort -u | while read path; do
  if [ -e "$path" ]; then
    cp -ru --parents "$path" "$TXTOS_DIR" || true
  fi
done


# Fetch and setup busybox
BUSYBOX_PATH="$TXTOS_DIR/bin/busybox"
wget -q https://github.com/Magisk-Modules-Repo/busybox-ndk/raw/refs/heads/master/busybox-arm64 -O "$BUSYBOX_PATH"
chmod +x "$BUSYBOX_PATH"

# Populate bin with busybox applets
echo "Installing busybox applets into $TXTOS_DIR/bin"
for applet in $("$BUSYBOX_PATH" --list); do
  ln -sf "busybox" "$TXTOS_DIR/bin/$applet"
done

# Write basic etc files
mkdir -p "$TXTOS_DIR/etc" "$TXTOS_DIR/root"
echo 'root:x:0:0:root:/root:/bin/sh' > "$TXTOS_DIR/etc/passwd"
echo 'root:$6$KRQ.XVFSWRQaZdsd$m5FKXTRFF6I94iCeGnDp1VBf0dL.4RM4Otgd1AnYgQaiqHHT5BBD9303vW13Nqnwfcy6dUogwLm5EbLq0DLOw/:19000:0:99999:7:::' > "$TXTOS_DIR/etc/shadow"
echo 'root:x:0:' > "$TXTOS_DIR/etc/group"
chmod 600 "$TXTOS_DIR/etc/shadow"
chmod 644 "$TXTOS_DIR/etc/passwd" "$TXTOS_DIR/etc/group"

# copy /lib to /system/{lib64, lib}
rm -rf $TXTOS_DIR/system/lib # just in case
cp -r $TXTOS_DIR/lib $TXTOS_DIR/system/lib
rm -rf $TXTOS_DIR/system/lib64 # also just in case
cp -r $TXTOS_DIR/lib $TXTOS_DIR/system/lib64

mkdir -p $TXTOS_DIR/linkerconfig # to subpress random warnings
touch $TXTOS_DIR/linkerconfig/ld.config.txt #
mkdir -p $TXTOS_DIR/system/usr/share/zoneinfo # sams
cp -r /system/usr/share/zoneinfo $TXTOS_DIR/system/usr/share/zoneinfo #

# Generate the startup script
RUN_SCRIPT="$LAST_CWD/startup.sh"
cwd=$(pwd)
echo "proot -0 -r $cwd/$TXTOS_DIR -b /dev -b /proc -w / /bin/sh -c 'export PATH=/bin; export HOME=/root; export LD_LIBRARY_PATH=/lib:/system/lib64; exec /bin/sh'" > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"
echo "✅ Done — startup script created at $RUN_SCRIPT"
