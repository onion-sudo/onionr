'''
    Onionr - Private P2P Communication

    Remove a transport address but don't ban them
'''
'''
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''
import sqlite3
from onionrplugins import onionrevents as events
from onionrutils import stringvalidators
from .. import dbfiles
def remove_address(address):
    '''
        Remove an address from the address database
    '''

    if stringvalidators.validate_transport(address):
        conn = sqlite3.connect(dbfiles.address_info_db, timeout=30)
        c = conn.cursor()
        t = (address,)
        c.execute('Delete from adders where address=?;', t)
        conn.commit()
        conn.close()

        #events.event('address_remove', data = {'address': address}, onionr = core_inst.onionrInst)
        return True
    else:
        return False