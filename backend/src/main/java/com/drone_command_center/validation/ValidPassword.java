package com.drone_command_center.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.*;

/**
 * Custom annotation for password validation.
 * Ensures password contains at least one uppercase letter, one lowercase letter,
 * one digit, and one special character.
 */
@Documented
@Constraint(validatedBy = PasswordValidator.class)
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidPassword {
    
    String message() default "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one digit, and one special character (@#$%^&+=!*)";
    
    Class<?>[] groups() default {};
    
    Class<? extends Payload>[] payload() default {};
}
