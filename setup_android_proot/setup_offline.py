#!/bin/bash                                          set -e                                                                                                    error() {                                              echo "Error: $@" >&2                                 exit 1
}                                                                                                         # Check dependencies                                 command -v proot >/dev/null 2>&1 || error "proot is not installed. Please pkg install proot"              command -v strace >/dev/null 2>&1 || error "strace is not installed. Please pkg install strace"
command -v wget >/dev/null 2>&1 || error "wget is not installed. Please pkg install wget"

# Save where we started
export LAST_CWD=$(pwd)                               
# Create temp dir                                    GO=$(mktemp -d) || error "failed to create temp dir" cd "$GO/.." || error "failed to cd to parent of temp dir"
rm -rf "$GO"                                                                                              # Go to tmp
cd "$PREFIX/tmp" || error "no such dir: $PREFIX/tmp" 
# Find txtosvfs_ directory                           TXTOS_DIR=$(find . -maxdepth 1 -type d -name "txtosvfs_*" | head -n1)                                     if [ -z "$TXTOS_DIR" ]; then                           error "no txtosvfs_ directory found — did you run os.py first?"
fi                                                                                                        # Prepare directories                                mkdir -p "$TXTOS_DIR/lib" "$TXTOS_DIR/system" "$TXTOS_DIR/bin" || error "failed to prepare directories"                                                        # Gather basic linker & shell                        ldd /bin/sh | awk '{print $3}' | xargs -I {} cp -u {} "$TXTOS_DIR/lib" || true                            cp -u /bin/sh "$TXTOS_DIR/bin"                       cp -u /bin/linker64 "$TXTOS_DIR/bin"                 cp -u /bin/linker64 "$TXTOS_DIR/lib"                 
# Copy into system                                   cp -r "$TXTOS_DIR/bin" "$TXTOS_DIR/system"           cp -r "$TXTOS_DIR/lib" "$TXTOS_DIR/system"
# Gather required libraries
cd $TXTOS_DIR/lib                                    cp /apex/com.android.runtime/lib64/bionic/libc.so ./ || true
cp /system/lib64/libm.so ./ || true
cp /system/lib64/libdl.so ./ || true                 cp /system/lib64/liblog.so ./ || true                cp /system/lib64/libstdc++.so ./ || true             cp /system/lib64/libz.so ./ || true                  cp /system/lib64/libandroid.so ./ || true            cp /system/lib64/libbinder.so ./ || true             cp /system/lib64/libutils.so ./ || true              cp /system/lib64/libcutils.so ./ || true             cp /system/lib64/libcrypto.so ./ || true             cp /system/lib64/libssl.so ./ || true
cp /system/lib64/libsqlite.so ./ || true
cp /system/lib64/libc++.so ./ || true
cp /system/lib64/libbase.so ./ || true
cp /system/lib64/libcgrouprc.so ./ || true           cp /system/lib64/libpcre2.so ./ || true              cp /system/lib64/libpackagelistparser.so ./ || true
cp /system/lib64/libprocessgroup.so ./ || true       cp /system/lib64/libselinux.so ./ || true            cd ../..
                                                     # Gather apex libs
echo "Scanning apex libs..."                         strace -f proot -r "$TXTOS_DIR" --bind=/dev --bind=/proc /bin/sh 2> log.txt || true
grep -oE '"/apex[^"]+"' log.txt | tr -d '"' | sort -u | while read path; do
  if [ -e "$path" ]; then
    cp -ru --parents "$path" "$TXTOS_DIR" || true      fi                                                 done

# Set up toybox                                      TOYBOX_PATH="$TXTOS_DIR/bin/toybox"
cp /system/bin/toybox "$TOYBOX_PATH"                 chmod +x "$TOYBOX_PATH"                              echo "Installing toybox applets into $TXTOS_DIR/bin"
for applet in $("$TOYBOX_PATH"); do                    ln -sf "toybox" "$TXTOS_DIR/bin/$applet"           done                                                 
# Write etc files
mkdir -p "$TXTOS_DIR/etc" "$TXTOS_DIR/root"          echo 'root:x:0:0:root:/root:/bin/sh' > "$TXTOS_DIR/etc/passwd"
echo 'root:$6$KRQ.XVFSWRQaZdsd$m5FKXTRFF6I94iCeGnDp1VBf0dL.4RM4Otgd1AnYgQaiqHHT5BBD9303vW13Nqnwfcy6dUogwLm5EbLq0DLOw/:19000:0:99999:7:::' > "$TXTOS_DIR/etc/shadow"                                                 echo 'root:x:0:' > "$TXTOS_DIR/etc/group"            chmod 600 "$TXTOS_DIR/etc/shadow"
chmod 644 "$TXTOS_DIR/etc/passwd" "$TXTOS_DIR/etc/group"                                                  touch $TXTOS_DIR/linkerconfig/ld.config.txt          # Copy lib into system/{lib,lib64}                   rm -rf "$TXTOS_DIR/system/lib" "$TXTOS_DIR/system/lib64"                                                  cp -r "$TXTOS_DIR/lib" "$TXTOS_DIR/system/lib"       cp -r "$TXTOS_DIR/lib" "$TXTOS_DIR/system/lib64"                                                          # Generate startup script                            RUN_SCRIPT="$LAST_CWD/startup.sh"                    cwd=$(pwd)                                           echo "proot -0 -r $cwd/$TXTOS_DIR -b /dev -b /proc -w / /bin/sh -c 'export PATH=/bin; export HOME=/root; export LD_LIBRARY_PATH=/lib:/system/lib64; exec /bin/sh'" > "$RUN_SCRIPT"
chmod +x "$RUN_SCRIPT"
echo "✅ Done — startup script created at $RUN_SCRIPT"
