import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';

import LoginScreen from './src/screens/LoginScreen';
import EstoqueScreen from './src/screens/EstoqueScreen';
import CadastroScreen from './src/screens/CadastroScreen';
import ScannerScreen from './src/screens/ScannerScreen';

const Stack = createNativeStackNavigator();

export default function App() {
    return (
        <NavigationContainer>
            <StatusBar style="light" backgroundColor="#0d6efd" />
            <Stack.Navigator
                initialRouteName="Login"
                screenOptions={{
                    headerStyle: {
                        backgroundColor: '#0d6efd',
                    },
                    headerTintColor: '#fff',
                    headerTitleStyle: {
                        fontWeight: 'bold',
                    },
                }}
            >
                <Stack.Screen
                    name="Login"
                    component={LoginScreen}
                    options={{ headerShown: false }}
                />
                <Stack.Screen
                    name="Estoque"
                    component={EstoqueScreen}
                    options={{
                        title: 'GALINT - Estoque',
                        headerBackVisible: false
                    }}
                />
                <Stack.Screen
                    name="Cadastro"
                    component={CadastroScreen}
                    options={{ title: 'Cadastrar Item' }}
                />
                <Stack.Screen
                    name="Scanner"
                    component={ScannerScreen}
                    options={{
                        title: 'Escanear Código',
                        headerTransparent: true
                    }}
                />
            </Stack.Navigator>
        </NavigationContainer>
    );
}
