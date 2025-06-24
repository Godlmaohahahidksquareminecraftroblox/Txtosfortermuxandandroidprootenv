#!/bin/bash
set -e

error() {
  echo "Error: $@" >&2
  exit 1
}
# look for needed utilities
command -v proot >/dev/null 2>&1 || error "proot is not installed. Please pkg install proot"
command -v strace >/dev/null 2>&1 || error "strace is not installed. Please pkg install strace"
command -v wget >/dev/null 2>&1 || error "wget is not installed. Please pkg install wget"

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

# Copy additional libraries toybox might need(offline version only)

cp /system/lib64/libbase.so ./         # Base Android lib
cp /system/lib64/libcgrouprc.so ./     # Cgroup rc
cp /system/lib64/libpcre2.so ./        # PCRE2 regex engine
cp /system/lib64/libpackagelistparser.so ./  # Package list parser
cd ../..

# Gather apex libs
echo "Scanning apex libs..."
strace -f proot -r "$TXTOS_DIR" --bind=/dev --bind=/proc /bin/sh 2> log.txt || true
grep -oE '"/apex[^"]+"' log.txt | tr -d '"' | sort -u | while read path; do
  if [ -e "$path" ]; then
    cp -ru --parents "$path" "$TXTOS_DIR" || true
  fi
done


# setup toybox
TOYBOX_PATH="$TXTOS_DIR/bin/toybox"
cp /system/bin/toybox "$TXTOS_DIR/bin/toybox"
cp /system/bin/toybox .
chmod +x "$BUSYBOX_PATH"

# Populate bin with busybox applets
echo "Installing toybox applets into $TXTOS_DIR/bin"
for applet in $("$TOYBOX_PATH"); do
  ln -sf "toybox" "$TXTOS_DIR/bin/$applet"
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
cp -f $TXTOS_DIR/lib $TXTOS_DIR/system/lib
rm -rf $TXTOS_DIR/system/lib64 # also just in case
cp -f $TXTOS_DIR/lib $TXTOS_DIR/system/lib64

# Generate the startup script
RUN_SCRIPT="$LAST_CWD/startup.sh"
cwd=$(pwd)
echo "proot -0 -r $cwd/$TXTOS_DIR -b /dev -b /proc -w / /bin/sh -c 'export PATH=/bin; export HOME=/root; export LD_LIBRARY_PATH=/lib:/system/lib64; exec /bin/sh'" > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"
echo "✅ Done — startup script created at $RUN_SCRIPT"
