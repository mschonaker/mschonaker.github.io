package com.example;

import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.Architectures.onionArchitecture;

@AnalyzeClasses(packages = "com.example")
class ArchitectureTest {

    @ArchTest
    static final ArchRule onion_architecture_is_respected = onionArchitecture()
            .domainModels("..domain.model..")
            .domainServices("..domain.service..")
            .applicationServices("..application..")
            .adapter("database", "..infrastructure.database..")
            .adapter("web", "..infrastructure.web..")
            .adapter("cli", "..infrastructure.cli..");

    @ArchTest
    static final ArchRule core_is_framework_free = noClasses()
            .that().resideInAnyPackage("com.example.domain..", "com.example.application..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("jakarta..", "io.quarkus..", "com.example.infrastructure..")
            .allowEmptyShould(true);
}
