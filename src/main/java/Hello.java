import jnr.ffi.LibraryLoader;
import jnr.ffi.Runtime;
import jnr.ffi.annotations.Pinned;
import java.util.Scanner;

public class Hello {
    public interface LibHello {
        void greet(@Pinned String name);
    }

    public static void main(String[] args) {
        LibHello lib = LibraryLoader.create(LibHello.class)
            .load("hello");
        
        System.out.print("Enter your name: ");
        Scanner scanner = new Scanner(System.in);
        String name = scanner.nextLine();
        
        lib.greet(name);
    }
}