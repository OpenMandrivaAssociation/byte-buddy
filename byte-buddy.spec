Name:		byte-buddy
Version:	1.18.17
Release:	1
Summary:	Runtime code generation for the Java virtual machine
Group:		Development/Java
License:	Apache-2.0
URL:		https://bytebuddy.net
Source0:	https://codeload.github.com/raphw/byte-buddy/tar.gz/refs/tags/byte-buddy-%{version}#/byte-buddy-%{version}.tar.gz
BuildArch:	noarch
# 1.17.7 split these out. This package ships neither the agent nor the plugin.
Obsoletes:	byte-buddy-agent < %{version}-%{release}
Obsoletes:	byte-buddy-dep < %{version}-%{release}
Obsoletes:	byte-buddy-maven-plugin < %{version}-%{release}
BuildRequires:	java-current-devel
BuildRequires:	python
BuildRequires:	sysjar
BuildRequires:	mvn(org.ow2.asm:asm)
BuildRequires:	mvn(org.ow2.asm:asm-commons)
BuildRequires:	mvn(org.ow2.asm:asm-tree)
BuildRequires:	mvn(org.ow2.asm:asm-analysis)
BuildRequires:	mvn(org.ow2.asm:asm-util)
BuildRequires:	mvn(net.java.dev.jna:jna)

%description
Byte Buddy generates classes while a program is running. This jar is
built against the system copy of ASM. The same file provides the Maven
artifacts byte-buddy and byte-buddy-dep. ASM stays in its own packages.
JNA is optional and is used only by the native class injector.

%prep
%setup -q -n byte-buddy-byte-buddy-%{version}
# The tag archive carries precompiled test classes. They are not inputs.
find . -name '*.class' -delete
find . -name '*.jar' -delete
if find . \( -name '*.class' -o -name '*.jar' \) | grep -q .; then
	echo "prebuilt bytecode remains" >&2
	exit 1
fi
rm -rf byte-buddy byte-buddy-agent byte-buddy-android byte-buddy-android-test \
	byte-buddy-benchmark byte-buddy-fuzz byte-buddy-gradle-plugin byte-buddy-maven-plugin

%build
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java}"
CP=/usr/share/java/asm.jar:/usr/share/java/asm-commons.jar:/usr/share/java/asm-tree.jar:/usr/share/java/asm-analysis.jar:/usr/share/java/asm-util.jar:/usr/share/java/jna.jar
mkdir -p build/stub-classes build/classes build/transformed build/driver
# These annotations are source-only markers. Their implementations are not
# packaged, so nothing in the jar refers to jsr305 or SpotBugs.
python - << 'PY'
from pathlib import Path
files = {
    "build/stub/edu/umd/cs/findbugs/annotations/SuppressFBWarnings.java": """
package edu.umd.cs.findbugs.annotations;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER, ElementType.CONSTRUCTOR, ElementType.LOCAL_VARIABLE, ElementType.PACKAGE})
public @interface SuppressFBWarnings {
	String[] value() default {};
	String justification() default "";
}
""",
    "build/stub/javax/annotation/meta/When.java": """
package javax.annotation.meta;
public enum When { ALWAYS, UNKNOWN, MAYBE, NEVER }
""",
    "build/stub/javax/annotation/Nonnull.java": """
package javax.annotation;
import javax.annotation.meta.When;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.METHOD, ElementType.PARAMETER, ElementType.FIELD, ElementType.TYPE, ElementType.PACKAGE})
public @interface Nonnull {
	When when() default When.ALWAYS;
}
""",
    "build/stub/javax/annotation/meta/TypeQualifierNickname.java": """
package javax.annotation.meta;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.ANNOTATION_TYPE)
public @interface TypeQualifierNickname {}
""",
    "build/stub/javax/annotation/meta/TypeQualifierDefault.java": """
package javax.annotation.meta;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.ANNOTATION_TYPE)
public @interface TypeQualifierDefault {
	ElementType[] value();
}
""",
}
for name, text in files.items():
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
PY
find build/stub -name '*.java' > build/stub-sources.list
"$JAVA_HOME/bin/javac" --release 8 -encoding UTF-8 -d build/stub-classes @build/stub-sources.list
find byte-buddy-dep/src/main/java -name '*.java' > build/sources.list
test "$(wc -l < build/sources.list)" -eq 343
"$JAVA_HOME/bin/javac" --release 8 -encoding UTF-8 \
	-cp "build/stub-classes:$CP" \
	-d build/classes @build/sources.list
# Upstream runs these plugins from the previous release's binary jar.
# Compile them from this tree instead, then rewrite the class files.
python - << 'PY'
from pathlib import Path
Path("build/Drive.java").write_text(r'''
import net.bytebuddy.ClassFileVersion;
import net.bytebuddy.build.AccessControllerPlugin;
import net.bytebuddy.build.CachedReturnPlugin;
import net.bytebuddy.build.DispatcherAnnotationPlugin;
import net.bytebuddy.build.EntryPoint;
import net.bytebuddy.build.HashCodeAndEqualsPlugin;
import net.bytebuddy.build.Plugin;
import net.bytebuddy.build.RepeatedAnnotationPlugin;
import net.bytebuddy.build.SafeVarargsPlugin;
import net.bytebuddy.dynamic.ClassFileLocator;
import net.bytebuddy.dynamic.scaffold.inline.MethodNameTransformer;

import java.io.File;
import java.util.Arrays;

public class Drive {
	public static void main(String[] args) throws Exception {
		Plugin.Engine engine = Plugin.Engine.Default.of(
				new EntryPoint.Unvalidated(EntryPoint.Default.REDEFINE),
				ClassFileVersion.JAVA_V8,
				MethodNameTransformer.Suffixing.withRandomSuffix())
			.with(new ClassFileLocator.Compound(
				ClassFileLocator.ForClassLoader.ofPlatformLoader(),
				ClassFileLocator.ForJarFile.of(new File(args[2])),
				ClassFileLocator.ForJarFile.of(new File(args[3])),
				ClassFileLocator.ForJarFile.of(new File(args[4])),
				ClassFileLocator.ForJarFile.of(new File(args[5])),
				ClassFileLocator.ForJarFile.of(new File(args[6])),
				ClassFileLocator.ForJarFile.of(new File(args[7]))));
		Plugin.Engine.Summary summary = engine.apply(
				new File(args[0]),
				new File(args[1]),
				Arrays.asList(
					new HashCodeAndEqualsPlugin.WithNonNullableFields("net.bytebuddy.utility.nullability.MaybeNull"),
					new CachedReturnPlugin(),
					new AccessControllerPlugin("net.bytebuddy.securitymanager"),
					new DispatcherAnnotationPlugin(),
					new RepeatedAnnotationPlugin(),
					new SafeVarargsPlugin()));
		System.out.println("transformed " + summary.getTransformed().size());
		System.out.println("failed " + summary.getFailed().size());
		System.out.println("unresolved " + summary.getUnresolved().size());
		for (String name : summary.getUnresolved()) {
			System.out.println("UNRESOLVED " + name);
		}
		for (java.util.Map.Entry<net.bytebuddy.description.type.TypeDescription, java.util.List<Throwable>> entry : summary.getFailed().entrySet()) {
			System.out.println("FAIL " + entry.getKey());
			for (Throwable throwable : entry.getValue()) {
				throwable.printStackTrace(System.out);
			}
		}
		if (!summary.getFailed().isEmpty() || !summary.getUnresolved().isEmpty()
				|| summary.getTransformed().size() != 1127) {
			System.exit(1);
		}
	}
}
'''.strip() + "\n", encoding="utf-8")
PY
"$JAVA_HOME/bin/javac" --release 8 -encoding UTF-8 -cp "build/classes:$CP" -d build/driver build/Drive.java
"$JAVA_HOME/bin/java" -cp "build/driver:build/classes:$CP" Drive \
	build/classes build/transformed \
	/usr/share/java/asm.jar \
	/usr/share/java/asm-commons.jar \
	/usr/share/java/asm-tree.jar \
	/usr/share/java/asm-analysis.jar \
	/usr/share/java/asm-util.jar \
	/usr/share/java/jna.jar
python - build/transformed << 'PY'
import os
import sys
root = sys.argv[1]
count = 0
for dirpath, _, files in os.walk(root):
    for name in files:
        if not name.endswith(".class"):
            continue
        count += 1
        data = open(os.path.join(dirpath, name), "rb").read(8)
        major = int.from_bytes(data[6:8], "big")
        if major != 52:
            raise SystemExit("class " + name + " has major " + str(major))
if count != 2996:
    raise SystemExit("class count " + str(count))
PY
cat > build/manifest.mf << 'EOF'
Manifest-Version: 1.0
Implementation-Title: net.bytebuddy
Implementation-Version: %{version}
Specification-Title: Byte Buddy
Specification-Version: %{version}
Automatic-Module-Name: net.bytebuddy
Main-Class: net.bytebuddy.build.Plugin$Engine$Default

EOF
"$JAVA_HOME/bin/jar" --create --manifest build/manifest.mf \
	--file build/byte-buddy.jar -C build/transformed .
cat > build/byte-buddy.pom << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>net.bytebuddy</groupId>
  <artifactId>byte-buddy</artifactId>
  <version>%{version}</version>
  <name>Byte Buddy</name>
  <description>Bytecode generation built against the system ASM, without relocating it.</description>
  <url>https://bytebuddy.net</url>
  <licenses>
    <license><name>Apache-2.0</name></license>
  </licenses>
  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.11.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.11.1</version>
    </dependency>
    <dependency>
      <groupId>codes.rafael.asmjdkbridge</groupId>
      <artifactId>asm-jdk-bridge</artifactId>
      <version>0.0.14</version>
      <optional>true</optional>
    </dependency>
    <dependency>
      <groupId>net.java.dev.jna</groupId>
      <artifactId>jna</artifactId>
      <version>5.19.1</version>
      <scope>provided</scope>
      <optional>true</optional>
    </dependency>
  </dependencies>
</project>
EOF

%install
sysjar install --buildroot %{buildroot} \
	--artifact build/byte-buddy.pom:build/byte-buddy.jar \
	--file-name byte-buddy \
	--alias net.bytebuddy:byte-buddy-dep \
	--filelist .mfiles

%check
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java}"
"$JAVA_HOME/bin/jar" tf build/byte-buddy.jar > build/jar-list.txt
grep -qx 'net/bytebuddy/ByteBuddy.class' build/jar-list.txt
grep -qx 'net/bytebuddy/build/EntryPoint$Unvalidated.class' build/jar-list.txt
if grep -q 'javax/annotation/' build/jar-list.txt; then
	echo "jar contains jsr305 stubs" >&2
	exit 1
fi
if grep -q 'edu/umd/' build/jar-list.txt; then
	echo "jar contains the SpotBugs stub" >&2
	exit 1
fi
if grep -q 'module-info.class' build/jar-list.txt; then
	echo "jar contains a module descriptor" >&2
	exit 1
fi
if grep -q 'META-INF/versions/' build/jar-list.txt; then
	echo "jar contains multi-release classes" >&2
	exit 1
fi
if grep -q 'net/bytebuddy/jar/' build/jar-list.txt; then
	echo "jar relocates ASM" >&2
	exit 1
fi
"$JAVA_HOME/bin/jar" --describe-module --file build/byte-buddy.jar > build/module.txt
grep -F 'net.bytebuddy automatic' build/module.txt
"$JAVA_HOME/bin/javap" -classpath build/byte-buddy.jar -public 'net.bytebuddy.build.EntryPoint$Unvalidated' > build/unvalidated.txt
grep -F 'equals(java.lang.Object)' build/unvalidated.txt
grep -F 'hashCode()' build/unvalidated.txt
python - << 'PY'
from pathlib import Path
Path("build/Probe.java").write_text(r'''
import net.bytebuddy.ByteBuddy;
import net.bytebuddy.build.EntryPoint;
import net.bytebuddy.description.method.MethodDescription;
import net.bytebuddy.description.type.TypeDescription;
import net.bytebuddy.implementation.FixedValue;
import net.bytebuddy.matcher.ElementMatchers;

public class Probe {
	public static void main(String[] args) throws Exception {
		EntryPoint same = new EntryPoint.Unvalidated(EntryPoint.Default.REDEFINE);
		EntryPoint copy = new EntryPoint.Unvalidated(EntryPoint.Default.REDEFINE);
		EntryPoint other = new EntryPoint.Unvalidated(EntryPoint.Default.REBASE);
		if (!same.equals(copy) || same.hashCode() != copy.hashCode()) {
			throw new AssertionError("equal delegates did not match");
		}
		if (same.equals(other) || same.equals(new Object()) || same.equals(null)) {
			throw new AssertionError("unequal values compared equal");
		}
		MethodDescription.SignatureToken left = new MethodDescription.SignatureToken("run",
				TypeDescription.ForLoadedType.of(void.class));
		MethodDescription.SignatureToken right = new MethodDescription.SignatureToken("run",
				TypeDescription.ForLoadedType.of(void.class));
		MethodDescription.SignatureToken stop = new MethodDescription.SignatureToken("stop",
				TypeDescription.ForLoadedType.of(void.class));
		if (!left.equals(right) || left.hashCode() != right.hashCode() || left.equals(stop)) {
			throw new AssertionError("signature token equality failed");
		}
		Class<?> type = new ByteBuddy()
				.subclass(Object.class)
				.name("probe.Made")
				.method(ElementMatchers.named("toString"))
				.intercept(FixedValue.value("ok"))
				.make()
				.load(Probe.class.getClassLoader())
				.getLoaded();
		Object instance = type.getDeclaredConstructor().newInstance();
		if (!"ok".equals(instance.toString())) {
			throw new AssertionError("generated toString was " + instance);
		}
		System.out.println("probe ok");
	}
}
'''.strip() + "\n", encoding="utf-8")
PY
"$JAVA_HOME/bin/javac" --release 8 -encoding UTF-8 \
	-cp build/byte-buddy.jar:/usr/share/java/asm.jar:/usr/share/java/asm-commons.jar \
	-d build/driver build/Probe.java
"$JAVA_HOME/bin/java" \
	-cp build/driver:build/byte-buddy.jar:/usr/share/java/asm.jar:/usr/share/java/asm-commons.jar \
	Probe

%files -f .mfiles
%license LICENSE NOTICE
%doc README.md release-notes.md
