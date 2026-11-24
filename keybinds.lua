-- Горячие клавиши звуковой панели Auraloom.
-- Клавиши можно переназначить в настройках FiveM (Settings -> Key Bindings):
--   sbplay1 ... sbplay33

local binds = {
    {cmd = 'sbplay01', key = '1', desc = 'Que chido, guay!'},
    {cmd = 'sbplay02', key = '2', desc = 'No manches, guay!'},
    {cmd = 'sbplay03', key = '3', desc = 'Orale, carnal!'},
    {cmd = 'sbplay04', key = '4', desc = 'A huevo!'},
    {cmd = 'sbplay05', key = '5', desc = 'Neta que no manches!'},
    {cmd = 'sbplay06', key = '6', desc = 'Que pedo, guay!'},
    {cmd = 'sbplay07', key = '7', desc = 'Pinche cabron!'},
    {cmd = 'sbplay08', key = '8', desc = 'Ya esta chido, aqui voy!'},
    {cmd = 'sbplay09', key = '9', desc = 'Chilango de mi corazon!'},
    {cmd = 'sbplay10', key = '0', desc = 'Ya ni me hable, por favor!'},
    {cmd = 'sbplay11', key = 'numpad1', desc = 'Arriba!'},
    {cmd = 'sbplay12', key = 'numpad2', desc = '¡Abajo!'},
    {cmd = 'sbplay13', key = 'numpad3', desc = 'No se mueva!'},
    {cmd = 'sbplay14', key = 'numpad4', desc = 'Manos arriba!'},
    {cmd = 'sbplay15', key = 'numpad5', desc = 'Alto! Alla se!'},
    {cmd = 'sbplay16', key = 'numpad6', desc = 'Suelte el arma!'},
    {cmd = 'sbplay17', key = 'numpad7', desc = '¡Dispara primero!'},
    {cmd = 'sbplay18', key = 'numpad8', desc = 'Me rindo!'},
    {cmd = 'sbplay19', key = 'numpad9', desc = '¡Auxilio!'},
    {cmd = 'sbplay20', key = 'f1', desc = 'Que me van a matar!'},
    {cmd = 'sbplay21', key = 'f2', desc = 'No me puedo mover!'},
    {cmd = 'sbplay22', key = 'f3', desc = 'Tengo un balazo en la pierna!'},
    {cmd = 'sbplay23', key = 'f4', desc = 'Socorro por favor!'},
    {cmd = 'sbplay24', key = 'f5', desc = 'Acepto mi destino!'},
    {cmd = 'sbplay25', key = 'f6', desc = 'No acepto, punto!'},
    {cmd = 'sbplay26', key = 'f7', desc = 'Aqui esta tu dinero, no te lopinees'},
    {cmd = 'sbplay27', key = 'f8', desc = 'Me late, no?'},
    {cmd = 'sbplay28', key = 'f9', desc = 'Eso no se hace aqui'},
    {cmd = 'sbplay29', key = 'f10', desc = 'Vete pal otro, te toca'},
    {cmd = 'sbplay30', key = 'f11', desc = 'Ya me dio hambre'},
    {cmd = 'sbplay31', key = 'f12', desc = 'Cafe con leche, por favor'},
    {cmd = 'sbplay32', key = 'pause', desc = 'eres un maldito maricón'},
    {cmd = 'sbplay33', key = 'scroll_lock', desc = 'hola mi dulce pan'},
}

for i, b in ipairs(binds) do
    RegisterKeyMapping(b.cmd, string.format('SB %02d - %s', i, b.desc), 'keyboard', b.key)
end
