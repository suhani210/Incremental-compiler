import java.util.*;

public class Main {

    static boolean isPrime(int n) {
        if (n < 2)
            return false;

        for (int i = 2; i * i <= n; i++) {
            if (n % i == 0)
                return false;
        }

        return true;
    }

    static boolean isBinaryPalindrome(int n) {
        String binary = Integer.toBinaryString(n);

        int left = 0;
        int right = binary.length() - 1;

        while (left < right) {
            if (binary.charAt(left) != binary.charAt(right))
                return false;

            left++;
            right--;
        }

        return true;
    }

    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);

        int N = sc.nextInt();
        int count = 0;

        for (int i = 1; i <= N; i++) {
            if (isPrime(i) && isBinaryPalindrome(i)) {
                count++;
            }
        }

        System.out.println(count);
    }
}