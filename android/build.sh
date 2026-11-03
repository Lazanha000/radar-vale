#!/bin/bash
# monta o APK sem Gradle/Android Studio: aapt2 -> javac -> d8 -> zipalign -> apksigner
# uso: bash android/build.sh   (gera android/radar-do-vale.apk)
set -e
cd "$(dirname "$0")"
P="$LOCALAPPDATA/Programs"
export JAVA_HOME="$P/jdk17/jdk-17.0.21+9" PATH="$P/jdk17/jdk-17.0.21+9/bin:$PATH"
BT="$P/android-sdk/build-tools/34.0.0" JAR="$P/android-sdk/platforms/android-34/android.jar"
rm -rf out && mkdir -p out/classes

python -c "
from PIL import Image, ImageDraw
s=192; im=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(im)
d.rounded_rectangle((0,0,s-1,s-1),40,fill='#17150f')
for r,w in ((70,10),(46,10)): d.arc((96-r,120-r,96+r,120+r),215,325,fill='#e58a5b',width=w)
d.ellipse((82,106,110,134),fill='#e58a5b')
im.save('res/mipmap/ic_launcher.png')"

"$BT/aapt2" compile --dir res -o out/res.zip
"$BT/aapt2" link -o out/base.apk -I "$JAR" --manifest AndroidManifest.xml out/res.zip --min-sdk-version 24 --target-sdk-version 34
javac -source 8 -target 8 -bootclasspath "$JAR" -nowarn -Xlint:-options -d out/classes src/br/radarvale/*.java
"$BT/d8.bat" --release --lib "$JAR" --min-api 24 --output out out/classes/br/radarvale/*.class
python -c "import zipfile; zipfile.ZipFile('out/base.apk','a').write('out/classes.dex','classes.dex')"
"$BT/zipalign.exe" -f -p 4 out/base.apk out/alinhado.apk

# shortcut: chave no padrão "debug" do Android (senha pública), serve para instalar por fora da Play Store; para publicar na loja, gerar chave própria
[ -f radar.keystore ] || keytool -genkeypair -keystore radar.keystore -storepass android -keypass android -alias radar \
  -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Radar do Vale" >/dev/null 2>&1
"$BT/apksigner.bat" sign --ks radar.keystore --ks-pass pass:android --out radar-do-vale.apk out/alinhado.apk
"$BT/apksigner.bat" verify radar-do-vale.apk && ls -la radar-do-vale.apk
