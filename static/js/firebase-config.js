import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
import { 
    getAuth, 
    GoogleAuthProvider, 
    signInWithPopup, 
    signOut, 
    onAuthStateChanged 
} from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";

// Web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyBwPDz_dI3uPy8H44hnz4Poemrrw-uAp-o",
    authDomain: "maintainiq-e33d4.firebaseapp.com",
    projectId: "maintainiq-e33d4",
    storageBucket: "maintainiq-e33d4.firebasestorage.app",
    messagingSenderId: "439626806692",
    appId: "1:439626806692:web:71f198d6b1024870287d31",
    measurementId: "G-HY6108LHJL"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

// Force account selector prompt on every sign-in
googleProvider.setCustomParameters({
    prompt: 'select_account'
});

export { 
    app, 
    auth, 
    googleProvider, 
    signInWithPopup, 
    signOut, 
    onAuthStateChanged 
};
